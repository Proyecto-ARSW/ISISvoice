"""Patient information endpoints."""
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import PatientCreate, PatientUpdate, PatientResponse
from app.services.patient_service import patient_service


router = APIRouter(prefix="/api/v1/patient", tags=["patient"])


# ========== Request/Response Models ==========

class PatientCreateRequest(BaseModel):
    """Request model for creating a patient."""
    cedula: str = Field(
        ...,
        min_length=6,
        max_length=15,
        description="Colombian ID number"
    )
    nombres: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Patient first names"
    )
    apellidos: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Patient last names"
    )
    fecha_nacimiento: date = Field(
        ...,
        description="Date of birth (YYYY-MM-DD)"
    )
    eps: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Health insurance provider"
    )
    genero: str = Field(
        ...,
        description="Gender (M, F, or Otro)"
    )
    direccion: Optional[str] = Field(
        None,
        max_length=200,
        description="Residential address"
    )
    ocupacion: Optional[str] = Field(
        None,
        max_length=100,
        description="Occupation"
    )
    enfermedades_cronicas: Optional[List[str]] = Field(
        None,
        description="List of chronic diseases"
    )
    detalles_importantes: Optional[str] = Field(
        None,
        max_length=500,
        description="Important medical details"
    )
    comentarios: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional comments"
    )


class PatientUpdateRequest(BaseModel):
    """Request model for updating a patient."""
    nombres: Optional[str] = Field(None, min_length=2, max_length=100)
    apellidos: Optional[str] = Field(None, min_length=2, max_length=100)
    eps: Optional[str] = Field(None, min_length=2, max_length=100)
    direccion: Optional[str] = Field(None, max_length=200)
    ocupacion: Optional[str] = Field(None, max_length=100)
    enfermedades_cronicas: Optional[List[str]] = None
    detalles_importantes: Optional[str] = Field(None, max_length=500)
    comentarios: Optional[str] = Field(None, max_length=500)


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    status_code: int


# ========== Endpoints ==========

@router.post(
    "/info",
    response_model=PatientResponse,
    summary="Create patient basic information",
    description="Register a new patient with basic demographic and medical information.",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def create_patient_info(request: PatientCreateRequest) -> PatientResponse:
    """
    Create a new patient record.
    
    Args:
        request: Patient information
    
    Returns:
        Patient record with timestamps
    """
    try:
        patient_data = PatientCreate(**request.model_dump())
        patient = await patient_service.create_patient(patient_data)
        return patient
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid patient data: {str(e)}")
    except Exception as e:
        if "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail=f"Patient with cedula {request.cedula} already exists"
            )
        raise HTTPException(status_code=500, detail=f"Error creating patient: {str(e)}")


@router.get(
    "/info/{cedula}",
    response_model=PatientResponse,
    summary="Get patient information",
    description="Retrieve patient basic information by cedula.",
    responses={404: {"model": ErrorResponse}}
)
async def get_patient_info(cedula: str) -> PatientResponse:
    """
    Get patient basic information.
    
    Args:
        cedula: Patient cedula
    
    Returns:
        Patient data
    """
    try:
        patient = await patient_service.get_patient(cedula)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with cedula {cedula} not found"
            )
        return patient
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving patient: {str(e)}")


@router.put(
    "/info/{cedula}",
    response_model=PatientResponse,
    summary="Update patient information",
    description="Update patient basic information by cedula.",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}}
)
async def update_patient_info(
    cedula: str,
    request: PatientUpdateRequest
) -> PatientResponse:
    """
    Update patient information.
    
    Args:
        cedula: Patient cedula
        request: Fields to update
    
    Returns:
        Updated patient data
    """
    try:
        # Check if patient exists first
        existing = await patient_service.get_patient(cedula)
        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Patient with cedula {cedula} not found"
            )
        
        update_data = PatientUpdate(**request.model_dump(exclude_unset=True))
        patient = await patient_service.update_patient(cedula, update_data)
        
        return patient
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid update data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating patient: {str(e)}")


@router.get(
    "/list",
    response_model=List[PatientResponse],
    summary="List all patients",
    description="Get paginated list of all patients.",
    responses={500: {"model": ErrorResponse}}
)
async def list_patients(
    limit: int = 100,
    skip: int = 0
) -> List[PatientResponse]:
    """
    List all patients with pagination.
    
    Args:
        limit: Maximum results (default: 100, max: 1000)
        skip: Records to skip (default: 0)
    
    Returns:
        List of patients
    """
    try:
        # Limit the maximum limit to prevent large queries
        limit = min(limit, 1000)
        patients = await patient_service.list_patients(limit=limit, skip=skip)
        return patients
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing patients: {str(e)}")


@router.get(
    "/exists/{cedula}",
    response_model=dict,
    summary="Check if patient exists",
    description="Check if a patient with given cedula exists.",
)
async def check_patient_exists(cedula: str) -> dict:
    """
    Check if patient exists.
    
    Args:
        cedula: Patient cedula
    
    Returns:
        {"exists": bool}
    """
    try:
        exists = await patient_service.patient_exists(cedula)
        return {"exists": exists, "cedula": cedula}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking patient: {str(e)}")
