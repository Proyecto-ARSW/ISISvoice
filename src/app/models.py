from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    model_config = ConfigDict(populate_by_name=True)

    procedure_id: str
    patient_id: str = Field(alias="patient_cedula")
    transcript: str
    input_type: Literal["text", "audio"]
    preliminary_history: TriageDataCore = Field(alias="triage_data")
    confidence_score: float
    status: str = "pending"
    vital_signs: VitalSignsCreate | None = None
    comments: list[Comment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    webhook_delivery: str = "pending"


class ProcedureRecordResponse(BaseModel):
    procedure_id: str
    patient_id: str
    transcript: str
    input_type: Literal["text", "audio"]
    preliminary_history: TriageDataCore
    confidence_score: float
    status: str
    vital_signs: VitalSignsCreate | None = None
    comments: list[Comment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    webhook_delivery: str = "pending"


class TriageRecordResponse(BaseModel):
    procedure_id: str
    patient_id: str
    preliminary_history: TriageDataCore
    status: str
