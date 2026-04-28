from typing import Literal

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from app.services.speech_service import transcribe_audio_bytes
from app.services.clinical_conversation_service import clinical_conversation_service
from pydantic import BaseModel, Field
from uuid import uuid4

router = APIRouter(prefix="/speech", tags=["speech"])

EMPTY_UPLOAD_ERROR = "Uploaded file is empty"


class ClinicalStartRequest(BaseModel):
    session_id: str | None = None


class ClinicalAIRequest(BaseModel):
    transcript: str = Field(..., description="Texto literal dicho por el paciente")
    session_id: str | None = None


class StructuredClinicalData(BaseModel):
    symptoms: str | None = Field(default=None, description="Sintomas principales")
    current_medications: str | None = Field(default=None, description="Medicamentos actuales o 'no'")
    pregnancy: str | None = Field(default=None, description="'si', 'no' o null")
    recent_trauma: str | None = Field(default=None, description="Trauma reciente o 'no'")
    possible_justification: str | None = Field(default=None, description="Posible justificante del padecimiento")


class TranscriptionResponse(BaseModel):
    transcription: str
    success: bool
    filename: str | None = None


class ClinicalTurnResponse(BaseModel):
    status: Literal["success", "no-speech"]
    session_id: str
    transcript: str
    assistant_reply: str
    clinical_data: StructuredClinicalData
    persistence: Literal["persisted", "buffered"]
    model_status: Literal["ok"]
    stage: str


class ClinicalStartResponse(BaseModel):
    status: Literal["session-started"]
    session_id: str
    assistant_reply: str
    clinical_data: StructuredClinicalData
    model_status: Literal["ok"]


class ClinicalFinalizeResponse(BaseModel):
    status: Literal["session-completed"]
    session_id: str
    final_clinical_history: dict
    persistence: Literal["persisted", "buffered"]
    model_status: Literal["ok"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    service: str
    dependencies: dict
    endpoints: list[str]


@router.post(
    "/transcribe-file",
    response_model=TranscriptionResponse,
    summary="Transcribir archivo de audio",
    description="Recibe un archivo de audio completo y devuelve la transcripcion en texto plano.",
)
async def transcribe_file(file: UploadFile = File(...)):
    """
    Endpoint tradicional para transcribir un archivo de audio completo.
    
    Args:
        file: Archivo de audio (WAV, MP3, M4A, etc.)
    
    Returns:
        {"transcription": "texto transcrito"}
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail=EMPTY_UPLOAD_ERROR)

        text = transcribe_audio_bytes(content, original_filename=file.filename)
        return {
            "transcription": text,
            "success": True,
            "filename": file.filename,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error transcribing file: {str(e)}")


@router.post(
    "/clinical/start",
    response_model=ClinicalStartResponse,
    summary="Iniciar sesion clinica",
    description="Crea o reutiliza una sesion clinica y devuelve la primera pregunta del flujo.",
)
async def clinical_start(payload: ClinicalStartRequest):
    """Inicia una sesion clinica por HTTPS."""
    session_id = payload.session_id or str(uuid4())
    await clinical_conversation_service.ensure_session(session_id)
    return {
        "status": "session-started",
        "session_id": session_id,
        "assistant_reply": "Iniciemos historia clinica. Cuéntame tu condicion o sintomas principales.",
        "clinical_data": {
            "symptoms": None,
            "current_medications": None,
            "pregnancy": None,
            "recent_trauma": None,
            "possible_justification": None,
        },
        "model_status": "ok",
    }


@router.post(
    "/clinical/audio",
    response_model=ClinicalTurnResponse,
    summary="Procesar audio en sesion clinica",
    description="Transcribe el audio de una sesion existente y avanza el flujo clinico.",
)
async def clinical_audio(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Recibe audio por HTTPS, transcribe y avanza la historia clinica.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=EMPTY_UPLOAD_ERROR)

    transcript = transcribe_audio_bytes(content, original_filename=file.filename)
    if transcript.startswith("[Error"):
        raise HTTPException(status_code=400, detail=transcript)

    result = await clinical_conversation_service.process_user_message(session_id, transcript)
    return {
        "status": result.get("status", "success"),
        "session_id": session_id,
        "transcript": result.get("transcript", ""),
        "assistant_reply": result.get("assistant_reply", ""),
        "clinical_data": result.get("structured_data", {}),
        "persistence": result.get("persistence", "buffered"),
        "model_status": "ok",
        "stage": result.get("stage", "identification"),
    }


@router.post(
    "/ia/analyze",
    response_model=ClinicalTurnResponse,
    summary="Analizar texto del paciente",
    description="Recibe texto libre (sin formato adicional) y devuelve la salida clinica estructurada.",
)
async def ai_analyze(payload: ClinicalAIRequest):
    """
    Endpoint de IA clinica por texto (solo lo dicho por paciente).
    """
    transcript = (payload.transcript or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript is required")

    session_id = payload.session_id or str(uuid4())
    await clinical_conversation_service.ensure_session(session_id)
    result = await clinical_conversation_service.process_user_message(session_id, transcript)

    return {
        "status": result.get("status", "success"),
        "session_id": session_id,
        "transcript": result.get("transcript", ""),
        "assistant_reply": result.get("assistant_reply", ""),
        "clinical_data": result.get("structured_data", {}),
        "persistence": result.get("persistence", "buffered"),
        "model_status": "ok",
        "stage": result.get("stage", "identification"),
    }


@router.post(
    "/flow/audio",
    response_model=ClinicalTurnResponse,
    summary="Flujo completo audio -> IA -> Mongo",
    description="Endpoint integral: transcribe audio, analiza datos clinicos y exige persistencia en MongoDB.",
)
async def flow_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
):
    """
    Flujo completo: transcribe audio + analiza + persiste en Mongo.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail=EMPTY_UPLOAD_ERROR)

    transcript = transcribe_audio_bytes(content, original_filename=file.filename)
    if transcript.startswith("[Error"):
        raise HTTPException(status_code=400, detail=transcript)

    active_session_id = session_id or str(uuid4())
    await clinical_conversation_service.ensure_session(active_session_id)
    result = await clinical_conversation_service.process_user_message(active_session_id, transcript)

    if result.get("persistence") != "persisted":
        raise HTTPException(
            status_code=503,
            detail="MongoDB no disponible para persistencia obligatoria en /speech/flow/audio",
        )

    return {
        "status": result.get("status", "success"),
        "session_id": active_session_id,
        "transcript": transcript,
        "assistant_reply": result.get("assistant_reply", ""),
        "clinical_data": result.get("structured_data", {}),
        "persistence": "persisted",
        "model_status": "ok",
        "stage": result.get("stage", "identification"),
    }


@router.post(
    "/clinical/finalize/{session_id}",
    response_model=ClinicalFinalizeResponse,
    summary="Finalizar sesion clinica",
    description="Consolida la historia clinica final de la sesion y la guarda en MongoDB.",
)
async def clinical_finalize(session_id: str):
    """Finaliza y consolida la historia clinica de una sesion."""
    final = await clinical_conversation_service.finalize_session(session_id)
    return {
        "status": "session-completed",
        "session_id": session_id,
        "final_clinical_history": final.get("final_clinical_history", {}),
        "persistence": final.get("persistence", "buffered"),
        "model_status": "ok",
    }


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado del servicio",
    description="Verifica estado general del servicio y conectividad de dependencias.",
)
async def health_check():
    """Endpoint para verificar que el servicio de speech está disponible."""
    dependencies = await clinical_conversation_service.health()
    deps_ok = dependencies.get("mongo", {}).get("status") == "up"
    return {
        "status": "healthy" if deps_ok else "degraded",
        "service": "speech-service",
        "dependencies": dependencies,
        "endpoints": [
            "POST /speech/transcribe-file - Transcribe un archivo de audio",
            "POST /speech/ia/analyze - Analiza texto del paciente y devuelve datos estructurados",
            "POST /speech/flow/audio - Flujo completo (audio -> transcripcion -> IA -> persistencia)",
            "POST /speech/clinical/start - Inicia una sesion clinica HTTPS",
            "POST /speech/clinical/audio - Envia audio del paciente y obtiene siguiente pregunta",
            "POST /speech/clinical/finalize/{session_id} - Consolida y guarda historia clinica final",
        ]
    }
