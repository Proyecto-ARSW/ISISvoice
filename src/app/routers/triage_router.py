"""Triage procedure endpoints."""
from typing import Literal, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from pydantic import BaseModel, Field

from app.models import (
    TriageRecordResponse,
    ProcedureRecordResponse,
    VitalSignsCreate,
    Comment,
)
from app.services.speech_service import transcribe_audio_bytes
from app.services.triage_service import triage_extraction_service
from app.services.procedure_service import procedure_service
from app.services.patient_service import patient_service


router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


# ========== Request/Response Models ==========

class TriageVoiceRequest(BaseModel):
    """Request model for voice-based triage input."""
    patient_cedula: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="Patient cedula"
    )


class TriageTextRequest(BaseModel):
    """Request model for text-based triage input."""
    patient_cedula: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="Patient cedula"
    )
    text_input: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Patient input text"
    )


class VitalSignsUpdateRequest(BaseModel):
    """Request model to add vital signs to a procedure."""
    frecuencia_cardiaca: Optional[int] = None
    temperatura: Optional[float] = None
    presion_arterial: Optional[str] = None
    saturacion_oxigeno: Optional[int] = None
    frecuencia_respiratoria: Optional[int] = None
    peso: Optional[float] = None
    talla: Optional[float] = None
    glucemia: Optional[int] = None


class CommentRequest(BaseModel):
    """Request model to add a comment to a procedure."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Comment text"
    )
    author: Optional[str] = Field(
        "system",
        max_length=100,
        description="Who added the comment"
    )


class TriageResponse(BaseModel):
    """Response model for successful triage creation."""
    procedure_id: str
    patient_cedula: str
    transcript: str
    triage_data: dict
    confidence_score: float
    input_type: Literal["voice", "text"]


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    status_code: int


# ========== Endpoints ==========

@router.post(
    "/voice-input",
    response_model=TriageResponse,
    summary="Process voice input for triage",
    description="Transcribe audio and extract triage data for patient clinical interview.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def process_voice_input(
    patient_cedula: str = Form(..., min_length=5, max_length=20),
    audio_file: UploadFile = File(..., description="Audio file (WAV, MP3, OGG, etc)")
) -> TriageResponse:
    """
    Process voice input for clinical triage.
    
    Steps:
    1. Transcribe audio using Whisper
    2. Extract triage data from transcript
    3. Save procedure record to MongoDB
    4. Return structured triage data
    """
    try:
        # Step 1: Transcribe audio
        audio_bytes = await audio_file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio file is empty")
        
        transcript = transcribe_audio_bytes(audio_bytes, original_filename=audio_file.filename)
        if not transcript or len(transcript.strip()) < 5:
            raise HTTPException(
                status_code=400,
                detail="Could not extract meaningful audio from file"
            )
        
        # Step 2: Extract triage data
        triage_data = triage_extraction_service.extract_triage_data(transcript)
        confidence = triage_extraction_service.get_confidence_score(triage_data)
        
        # Override cedula if not extracted (use from parameter)
        if not triage_data.identification_number:
            triage_data.identification_number = patient_cedula
        
        # Step 3: Generate procedure ID
        procedure_id = triage_extraction_service.generate_procedure_id(
            triage_data.identification_number or patient_cedula
        )
        
        # Step 4: Save to MongoDB
        await procedure_service.create_triage_record(
            procedure_id=procedure_id,
            patient_cedula=patient_cedula,
            transcript=transcript,
            input_type="voice",
            triage_data_dict=triage_data.model_dump(),
            confidence_score=confidence,
        )
        
        return TriageResponse(
            procedure_id=procedure_id,
            patient_cedula=patient_cedula,
            transcript=transcript,
            triage_data=triage_data.model_dump(),
            confidence_score=confidence,
            input_type="voice",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing voice: {str(e)}")


@router.post(
    "/text-input",
    response_model=TriageResponse,
    summary="Process text input for triage",
    description="Extract triage data from patient text input.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def process_text_input(request: TriageTextRequest) -> TriageResponse:
    """
    Process text input for clinical triage.
    
    Steps:
    1. Extract triage data from text
    2. Save procedure record to MongoDB
    3. Return structured triage data
    """
    try:
        # Step 1: Extract triage data
        triage_data = triage_extraction_service.extract_triage_data(request.text_input)
        confidence = triage_extraction_service.get_confidence_score(triage_data)
        
        # Override cedula if not extracted (use from parameter)
        if not triage_data.identification_number:
            triage_data.identification_number = request.patient_cedula
        
        # Step 2: Generate procedure ID
        procedure_id = triage_extraction_service.generate_procedure_id(
            triage_data.identification_number or request.patient_cedula
        )
        
        # Step 3: Save to MongoDB
        await procedure_service.create_triage_record(
            procedure_id=procedure_id,
            patient_cedula=request.patient_cedula,
            transcript=request.text_input,
            input_type="text",
            triage_data_dict=triage_data.model_dump(),
            confidence_score=confidence,
        )
        
        return TriageResponse(
            procedure_id=procedure_id,
            patient_cedula=request.patient_cedula,
            transcript=request.text_input,
            triage_data=triage_data.model_dump(),
            confidence_score=confidence,
            input_type="text",
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing text: {str(e)}")


@router.get(
    "/record/{cedula}",
    response_model=list[ProcedureRecordResponse],
    summary="Get triage records by cedula",
    description="Retrieve all triage procedures for a patient by cedula.",
    responses={404: {"model": ErrorResponse}}
)
async def get_triage_records(cedula: str) -> list[ProcedureRecordResponse]:
    """
    Get all triage records for a patient.
    
    Args:
        cedula: Patient cedula
    
    Returns:
        List of procedure records sorted by creation time (newest first)
    """
    try:
        procedures = await procedure_service.get_procedures_by_cedula(cedula, limit=50)
        if not procedures:
            raise HTTPException(
                status_code=404,
                detail=f"No procedures found for cedula {cedula}"
            )
        return [ProcedureRecordResponse(**p.model_dump()) for p in procedures]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving records: {str(e)}")


@router.get(
    "/procedure/{procedure_id}",
    response_model=ProcedureRecordResponse,
    summary="Get specific procedure record",
    description="Retrieve a specific triage procedure by ID.",
    responses={404: {"model": ErrorResponse}}
)
async def get_procedure(procedure_id: str) -> ProcedureRecordResponse:
    """
    Get a specific procedure by ID.
    
    Args:
        procedure_id: Procedure ID
    
    Returns:
        Procedure record with all details
    """
    try:
        procedure = await procedure_service.get_procedure(procedure_id)
        if not procedure:
            raise HTTPException(
                status_code=404,
                detail=f"Procedure {procedure_id} not found"
            )
        return ProcedureRecordResponse(**procedure.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving procedure: {str(e)}")


@router.put(
    "/record/{procedure_id}/vital-signs",
    response_model=ProcedureRecordResponse,
    summary="Add/update vital signs",
    description="Add or update vital signs for a procedure record.",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}}
)
async def update_vital_signs(
    procedure_id: str,
    request: VitalSignsUpdateRequest
) -> ProcedureRecordResponse:
    """
    Add or update vital signs for a procedure.
    
    Args:
        procedure_id: Procedure ID
        request: Vital signs data (all fields optional)
    
    Returns:
        Updated procedure record
    """
    try:
        vital_signs = VitalSignsCreate(**request.model_dump())
        procedure = await procedure_service.add_vital_signs(procedure_id, vital_signs)
        
        if not procedure:
            raise HTTPException(
                status_code=404,
                detail=f"Procedure {procedure_id} not found"
            )
        
        return ProcedureRecordResponse(**procedure.model_dump())
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid vital signs: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating vital signs: {str(e)}")


@router.post(
    "/record/{procedure_id}/comment",
    response_model=ProcedureRecordResponse,
    summary="Add comment to procedure",
    description="Add a comment to a procedure record.",
    responses={404: {"model": ErrorResponse}}
)
async def add_procedure_comment(
    procedure_id: str,
    request: CommentRequest
) -> ProcedureRecordResponse:
    """
    Add a comment to a procedure.
    
    Args:
        procedure_id: Procedure ID
        request: Comment text and author
    
    Returns:
        Updated procedure record
    """
    try:
        procedure = await procedure_service.add_comment(
            procedure_id,
            request.text,
            request.author
        )
        
        if not procedure:
            raise HTTPException(
                status_code=404,
                detail=f"Procedure {procedure_id} not found"
            )
        
        return ProcedureRecordResponse(**procedure.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding comment: {str(e)}")


@router.put(
    "/record/{procedure_id}/close",
    response_model=ProcedureRecordResponse,
    summary="Close procedure",
    description="Mark procedure as closed/completed.",
    responses={404: {"model": ErrorResponse}}
)
async def close_procedure(
    procedure_id: str,
    final_notes: Optional[str] = None
) -> ProcedureRecordResponse:
    """
    Close a procedure record.
    
    Args:
        procedure_id: Procedure ID
        final_notes: Optional final clinical notes
    
    Returns:
        Updated procedure record
    """
    try:
        procedure = await procedure_service.close_procedure(procedure_id, final_notes)
        
        if not procedure:
            raise HTTPException(
                status_code=404,
                detail=f"Procedure {procedure_id} not found"
            )
        
        return ProcedureRecordResponse(**procedure.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error closing procedure: {str(e)}")
