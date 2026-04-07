from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    cedula: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    eps: str
    genero: str
    direccion: str | None = None
    ocupacion: str | None = None
    enfermedades_cronicas: list[str] | None = None
    detalles_importantes: str | None = None
    comentarios: str | None = None


class PatientUpdate(BaseModel):
    nombres: str | None = None
    apellidos: str | None = None
    eps: str | None = None
    direccion: str | None = None
    ocupacion: str | None = None
    enfermedades_cronicas: list[str] | None = None
    detalles_importantes: str | None = None
    comentarios: str | None = None


class PatientResponse(BaseModel):
    cedula: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date
    eps: str
    genero: str
    direccion: str | None = None
    ocupacion: str | None = None
    enfermedades_cronicas: list[str] | None = None
    detalles_importantes: str | None = None
    comentarios: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TriageDataCore(BaseModel):
    idpaciente: str
    sintomas: list[str] = Field(default_factory=list)
    embarazo: bool = False
    antecedentes: list[str] = Field(default_factory=list)
    posiblesCausas: list[str] = Field(default_factory=list)
    comentario: str = ""
    nivelPrioridad: int = Field(default=3, ge=1, le=5)
    comentariosIA: str = ""
    advertenciaIA: str = "Contenido generado con IA; puede contener errores."


class VitalSignsCreate(BaseModel):
    temperature_c: float | None = None
    heart_rate_bpm: int | None = None
    respiratory_rate_bpm: int | None = None
    systolic_bp_mmhg: int | None = None
    diastolic_bp_mmhg: int | None = None
    oxygen_saturation_pct: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None


class Comment(BaseModel):
    id: str
    comment: str
    author: str = "system"
    created_at: datetime


class ProcedureRecord(BaseModel):
    procedure_id: str
    patient_cedula: str
    transcript: str
    input_type: Literal["text", "audio"]
    triage_data: TriageDataCore
    confidence_score: float
    status: str = "triage_completed"
    vital_signs: VitalSignsCreate | None = None
    comments: list[Comment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProcedureRecordResponse(BaseModel):
    procedure_id: str
    patient_cedula: str
    transcript: str
    input_type: Literal["text", "audio"]
    triage_data: TriageDataCore
    confidence_score: float
    status: str
    vital_signs: VitalSignsCreate | None = None
    comments: list[Comment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TriageRecordResponse(BaseModel):
    procedure_id: str
    patient_cedula: str
    triage_data: TriageDataCore
    status: str
