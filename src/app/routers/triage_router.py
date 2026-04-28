"""Triage endpoints protected with JWT from main backend."""
from __future__ import annotations

import base64
import binascii
from typing import Annotated
from typing import Any
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import AuthUser, JwtRole, require_roles
from app.models import ProcedureRecordResponse, TriageDataCore, VitalSignsCreate
from app.services.procedure_service import procedure_service
from app.services.speech_service import transcribe_audio_bytes
from app.services.triage_service import triage_extraction_service


router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


class TriageTextRequest(BaseModel):
    text_input: str = Field(..., min_length=1, max_length=3000)


class TriageAudioBase64Request(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    file_name: Optional[str] = None
    mime_type: Optional[str] = None


class VitalSignsUpdateRequest(BaseModel):
    temperature_c: Optional[float] = None
    heart_rate_bpm: Optional[int] = None
    respiratory_rate_bpm: Optional[int] = None
    systolic_bp_mmhg: Optional[int] = None
    diastolic_bp_mmhg: Optional[int] = None
    oxygen_saturation_pct: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None


class CommentRequest(BaseModel):
    comment: str = Field(..., min_length=1, max_length=1000)


class CloseProcedureRequest(BaseModel):
    close_reason: Optional[str] = None


class TriageIntakeResponse(BaseModel):
    procedure_id: str
    patient_id: str
    status: str
    recommendation: str


class TriageListResponse(BaseModel):
    items: list[ProcedureRecordResponse]


def _get_body_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _parse_text_request(payload: dict[str, Any]) -> TriageTextRequest:
    text_input = _get_body_value(payload, "text_input", "textInput", "text", "symptoms", "transcript")
    if not isinstance(text_input, str):
        raise HTTPException(status_code=422, detail="Field required: text_input")
    return TriageTextRequest(text_input=text_input)


def _parse_audio_request(payload: dict[str, Any]) -> TriageAudioBase64Request:
    audio_base64 = _get_body_value(payload, "audio_base64", "audioBase64")
    if not isinstance(audio_base64, str):
        raise HTTPException(status_code=422, detail="Field required: audio_base64")

    file_name = _get_body_value(payload, "file_name", "fileName")
    mime_type = _get_body_value(payload, "mime_type", "mimeType")

    return TriageAudioBase64Request(
        audio_base64=audio_base64,
        file_name=file_name if isinstance(file_name, str) else None,
        mime_type=mime_type if isinstance(mime_type, str) else None,
    )


def _ensure_patient_access(user: AuthUser, owner_patient_id: str) -> None:
    if user.role == JwtRole.PACIENTE and user.user_id != owner_patient_id:
        raise HTTPException(status_code=403, detail="No puedes consultar historias de otro paciente")


def _decode_audio_payload(payload: str) -> bytes:
    raw_value = payload.strip()
    if "," in raw_value and raw_value.startswith("data:"):
        raw_value = raw_value.split(",", 1)[1]

    try:
        return base64.b64decode(raw_value, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="audioBase64 no contiene un audio valido") from exc


@router.post(
    "/symptoms/text",
    responses={
        400: {"description": "Solicitud invalida"},
        401: {"description": "No autenticado"},
        422: {"description": "Falta el campo text_input"},
    },
)
async def ingest_symptoms_text(
    request: dict[str, Any],
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.PACIENTE))],
) -> TriageIntakeResponse:
    parsed_request = _parse_text_request(request)
    transcript = parsed_request.text_input.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="text_input es obligatorio")

    triage_data = await triage_extraction_service.extract_preliminary_history(transcript)
    confidence = triage_extraction_service.get_confidence_score(triage_data)
    procedure_id = triage_extraction_service.generate_procedure_id(user.user_id)

    await procedure_service.create_triage_record(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        transcript=transcript,
        input_type="text",
        triage_data_dict=triage_data.model_dump(),
        confidence_score=confidence,
    )

    return TriageIntakeResponse(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        status="pending",
        recommendation=triage_extraction_service.build_recommendation(triage_data),
    )


@router.post(
    "/symptoms/audio/base64",
    responses={
        400: {"description": "Audio invalido"},
        401: {"description": "No autenticado"},
        422: {"description": "Falta el campo audio_base64"},
    },
)
async def ingest_symptoms_audio_base64(
    request: dict[str, Any],
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.PACIENTE))],
) -> TriageIntakeResponse:
    parsed_request = _parse_audio_request(request)
    audio_bytes = _decode_audio_payload(parsed_request.audio_base64)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="El audio esta vacio")

    transcript = transcribe_audio_bytes(audio_bytes, original_filename=parsed_request.file_name)
    if not transcript or len(transcript.strip()) < 5:
        raise HTTPException(status_code=400, detail="No fue posible obtener texto util desde el audio")

    triage_data = await triage_extraction_service.extract_preliminary_history(transcript)
    confidence = triage_extraction_service.get_confidence_score(triage_data)
    procedure_id = triage_extraction_service.generate_procedure_id(user.user_id)

    await procedure_service.create_triage_record(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        transcript=transcript,
        input_type="audio",
        triage_data_dict=triage_data.model_dump(),
        confidence_score=confidence,
    )

    return TriageIntakeResponse(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        status="pending",
        recommendation=triage_extraction_service.build_recommendation(triage_data),
    )


@router.post("/symptoms/audio", responses={400: {"description": "Audio invalido"}, 401: {"description": "No autenticado"}})
async def ingest_symptoms_audio(
    audio_file: Annotated[UploadFile, File(..., description="Audio con sintomas del paciente")],
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.PACIENTE))],
) -> TriageIntakeResponse:
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="El archivo de audio esta vacio")

    transcript = transcribe_audio_bytes(audio_bytes, original_filename=audio_file.filename)
    if not transcript or len(transcript.strip()) < 5:
        raise HTTPException(status_code=400, detail="No fue posible obtener texto util desde el audio")

    triage_data = await triage_extraction_service.extract_preliminary_history(transcript)
    confidence = triage_extraction_service.get_confidence_score(triage_data)
    procedure_id = triage_extraction_service.generate_procedure_id(user.user_id)

    await procedure_service.create_triage_record(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        transcript=transcript,
        input_type="audio",
        triage_data_dict=triage_data.model_dump(),
        confidence_score=confidence,
    )

    return TriageIntakeResponse(
        procedure_id=procedure_id,
        patient_id=user.user_id,
        status="pending",
        recommendation=triage_extraction_service.build_recommendation(triage_data),
    )


@router.put(
    "/record/{procedure_id}/vital-signs",
    responses={404: {"description": "Procedimiento no encontrado"}, 403: {"description": "Sin permisos"}},
)
async def update_vital_signs(
    procedure_id: str,
    request: VitalSignsUpdateRequest,
    _: Annotated[AuthUser, Depends(require_roles(JwtRole.ENFERMERO, JwtRole.MEDICO))],
) -> ProcedureRecordResponse:
    vital_signs = VitalSignsCreate(**request.model_dump())
    procedure = await procedure_service.add_vital_signs(procedure_id, vital_signs)
    if not procedure:
        raise HTTPException(status_code=404, detail=f"Procedimiento {procedure_id} no encontrado")
    return ProcedureRecordResponse(**procedure.model_dump())


@router.get(
    "/record/{procedure_id}/preliminary-history",
    responses={404: {"description": "Procedimiento no encontrado"}, 403: {"description": "Sin permisos"}},
)
async def get_preliminary_history(
    procedure_id: str,
    user: Annotated[
        AuthUser,
        Depends(require_roles(JwtRole.PACIENTE, JwtRole.ENFERMERO, JwtRole.MEDICO)),
    ],
) -> TriageDataCore:
    procedure = await procedure_service.get_procedure(procedure_id)
    if not procedure:
        raise HTTPException(status_code=404, detail=f"Procedimiento {procedure_id} no encontrado")

    _ensure_patient_access(user, procedure.patient_id)
    return procedure.preliminary_history


@router.get(
    "/procedure/{procedure_id}",
    responses={404: {"description": "Procedimiento no encontrado"}, 403: {"description": "Sin permisos"}},
)
async def get_procedure(
    procedure_id: str,
    user: Annotated[
        AuthUser,
        Depends(require_roles(JwtRole.PACIENTE, JwtRole.ENFERMERO, JwtRole.MEDICO)),
    ],
) -> ProcedureRecordResponse:
    procedure = await procedure_service.get_procedure(procedure_id)
    if not procedure:
        raise HTTPException(status_code=404, detail=f"Procedimiento {procedure_id} no encontrado")

    _ensure_patient_access(user, procedure.patient_id)
    return ProcedureRecordResponse(**procedure.model_dump())


@router.get(
    "/procedures/my",
    responses={401: {"description": "No autenticado"}},
)
async def get_my_procedures(
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.PACIENTE))],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TriageListResponse:
    procedures = await procedure_service.get_patient_procedures(user.user_id, limit=limit)
    return TriageListResponse(
        items=[ProcedureRecordResponse(**procedure.model_dump()) for procedure in procedures],
    )


@router.get(
    "/procedures/me",
    responses={401: {"description": "No autenticado"}},
)
async def get_my_procedures_legacy(
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.PACIENTE))],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TriageListResponse:
    procedures = await procedure_service.get_patient_procedures(user.user_id, limit=limit)
    return TriageListResponse(
        items=[ProcedureRecordResponse(**procedure.model_dump()) for procedure in procedures],
    )


@router.get(
    "/records",
    responses={401: {"description": "No autenticado"}},
)
async def list_triage_records(
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.ENFERMERO, JwtRole.MEDICO, JwtRole.ADMIN))],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    status: Annotated[str | None, Query()] = None,
) -> TriageListResponse:
    if status is not None and status not in {"pending", "resolved", "closed", "vital_signs_recorded", "all"}:
        raise HTTPException(status_code=400, detail="status invalido")

    effective_status = None if status in {None, "all"} else status
    records = await procedure_service.list_procedures(limit=limit, status=effective_status)
    return TriageListResponse(
        items=[ProcedureRecordResponse(**record.model_dump()) for record in records],
    )


@router.post(
    "/record/{procedure_id}/comment",
    responses={404: {"description": "Procedimiento no encontrado"}, 403: {"description": "Sin permisos"}},
)
async def add_procedure_comment(
    procedure_id: str,
    request: CommentRequest,
    user: Annotated[AuthUser, Depends(require_roles(JwtRole.ENFERMERO, JwtRole.MEDICO))],
) -> ProcedureRecordResponse:
    procedure = await procedure_service.add_comment(
        procedure_id,
        request.comment,
        user.role,
    )
    if not procedure:
        raise HTTPException(status_code=404, detail=f"Procedimiento {procedure_id} no encontrado")
    return ProcedureRecordResponse(**procedure.model_dump())


@router.post(
    "/record/{procedure_id}/close",
    responses={404: {"description": "Procedimiento no encontrado"}, 403: {"description": "Sin permisos"}},
)
async def close_procedure(
    procedure_id: str,
    request: CloseProcedureRequest,
    _: Annotated[AuthUser, Depends(require_roles(JwtRole.MEDICO, JwtRole.ENFERMERO))],
) -> ProcedureRecordResponse:
    procedure = await procedure_service.close_procedure(
        procedure_id,
        final_notes=request.close_reason,
    )
    if not procedure:
        raise HTTPException(status_code=404, detail=f"Procedimiento {procedure_id} no encontrado")
    return ProcedureRecordResponse(**procedure.model_dump())
