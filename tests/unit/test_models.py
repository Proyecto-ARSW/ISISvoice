"""Tests for Pydantic models in app/models.py."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    Comment,
    PatientCreate,
    PatientUpdate,
    ProcedureRecord,
    ProcedureRecordResponse,
    TriageDataCore,
    TriageRecordResponse,
    VitalSignsCreate,
)

_NOW = datetime.now(timezone.utc)


# ─── PatientCreate ────────────────────────────────────────────────────────────

class TestPatientCreate:
    def test_valid_minimal(self):
        p = PatientCreate(
            cedula="12345678",
            nombres="Juan",
            apellidos="Perez",
            fecha_nacimiento=date(1990, 1, 15),
            eps="Sura",
            genero="M",
        )
        assert p.cedula == "12345678"
        assert p.nombres == "Juan"

    def test_missing_cedula_raises(self):
        with pytest.raises(ValidationError):
            PatientCreate(
                nombres="Juan",
                apellidos="Perez",
                fecha_nacimiento=date(1990, 1, 1),
                eps="X",
                genero="M",
            )

    def test_optional_fields_default_none(self):
        p = PatientCreate(
            cedula="1",
            nombres="A",
            apellidos="B",
            fecha_nacimiento=date(2000, 6, 1),
            eps="EPS",
            genero="F",
        )
        assert p.direccion is None
        assert p.ocupacion is None
        assert p.enfermedades_cronicas is None
        assert p.detalles_importantes is None
        assert p.comentarios is None

    def test_with_all_optional_fields(self):
        p = PatientCreate(
            cedula="99",
            nombres="Maria",
            apellidos="Lopez",
            fecha_nacimiento=date(1985, 3, 20),
            eps="Compensar",
            genero="F",
            direccion="Calle 1",
            ocupacion="Docente",
            enfermedades_cronicas=["diabetes"],
            detalles_importantes="alergia a penicilina",
            comentarios="paciente estable",
        )
        assert p.enfermedades_cronicas == ["diabetes"]
        assert p.detalles_importantes == "alergia a penicilina"


# ─── PatientUpdate ────────────────────────────────────────────────────────────

class TestPatientUpdate:
    def test_all_optional_empty(self):
        p = PatientUpdate()
        assert p.nombres is None
        assert p.apellidos is None
        assert p.eps is None

    def test_partial_update(self):
        p = PatientUpdate(nombres="Carlos", eps="Sanitas")
        assert p.nombres == "Carlos"
        assert p.eps == "Sanitas"
        assert p.apellidos is None


# ─── TriageDataCore ───────────────────────────────────────────────────────────

class TestTriageDataCore:
    def test_defaults(self):
        t = TriageDataCore()
        assert t.sintomas == []
        assert t.embarazo is False
        assert t.antecedentes == []
        assert t.posiblesCausas == []
        assert t.comentario == ""
        assert t.nivelPrioridad == 3
        assert t.comentariosIA == ""
        assert "IA" in t.advertenciaIA

    def test_nivel_prioridad_below_1_raises(self):
        with pytest.raises(ValidationError):
            TriageDataCore(nivelPrioridad=0)

    def test_nivel_prioridad_above_5_raises(self):
        with pytest.raises(ValidationError):
            TriageDataCore(nivelPrioridad=6)

    def test_nivel_prioridad_boundary_1(self):
        assert TriageDataCore(nivelPrioridad=1).nivelPrioridad == 1

    def test_nivel_prioridad_boundary_5(self):
        assert TriageDataCore(nivelPrioridad=5).nivelPrioridad == 5

    def test_with_full_data(self):
        t = TriageDataCore(
            sintomas=["fiebre", "cefalea"],
            embarazo=True,
            antecedentes=["diabetes"],
            posiblesCausas=["dengue"],
            comentario="paciente refiere fiebre",
            nivelPrioridad=2,
            comentariosIA="IA: alta prioridad",
        )
        assert len(t.sintomas) == 2
        assert t.embarazo is True
        assert t.nivelPrioridad == 2


# ─── VitalSignsCreate ─────────────────────────────────────────────────────────

class TestVitalSignsCreate:
    def test_all_none_by_default(self):
        v = VitalSignsCreate()
        for field in ["temperature_c", "heart_rate_bpm", "respiratory_rate_bpm",
                      "systolic_bp_mmhg", "diastolic_bp_mmhg", "oxygen_saturation_pct",
                      "weight_kg", "height_cm"]:
            assert getattr(v, field) is None

    def test_with_values(self):
        v = VitalSignsCreate(
            temperature_c=37.5,
            heart_rate_bpm=80,
            oxygen_saturation_pct=98,
            systolic_bp_mmhg=120,
            diastolic_bp_mmhg=80,
        )
        assert v.temperature_c == 37.5
        assert v.heart_rate_bpm == 80
        assert v.oxygen_saturation_pct == 98


# ─── Comment ──────────────────────────────────────────────────────────────────

class TestComment:
    def test_default_author_system(self):
        c = Comment(id="1", comment="paciente estable", created_at=_NOW)
        assert c.author == "system"

    def test_custom_author(self):
        c = Comment(id="2", comment="nota médica", author="MEDICO", created_at=_NOW)
        assert c.author == "MEDICO"

    def test_requires_id_and_comment(self):
        with pytest.raises(ValidationError):
            Comment(created_at=_NOW)


# ─── ProcedureRecord ──────────────────────────────────────────────────────────

class TestProcedureRecord:
    def test_alias_patient_cedula_maps_to_patient_id(self):
        record = ProcedureRecord(
            procedure_id="proc_001",
            patient_cedula="12345678",
            transcript="tengo fiebre",
            input_type="text",
            triage_data=TriageDataCore(),
            confidence_score=0.75,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert record.patient_id == "12345678"

    def test_alias_triage_data_maps_to_preliminary_history(self):
        triage = TriageDataCore(sintomas=["fiebre"])
        record = ProcedureRecord(
            procedure_id="proc_002",
            patient_cedula="123",
            transcript="test",
            input_type="text",
            triage_data=triage,
            confidence_score=0.5,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert record.preliminary_history.sintomas == ["fiebre"]

    def test_default_status_pending(self):
        record = ProcedureRecord(
            procedure_id="p",
            patient_cedula="1",
            transcript="t",
            input_type="text",
            triage_data=TriageDataCore(),
            confidence_score=0.0,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert record.status == "pending"
        assert record.comments == []
        assert record.webhook_delivery == "pending"
        assert record.vital_signs is None

    def test_input_type_audio(self):
        record = ProcedureRecord(
            procedure_id="p2",
            patient_cedula="2",
            transcript="audio transcribed",
            input_type="audio",
            triage_data=TriageDataCore(),
            confidence_score=0.8,
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert record.input_type == "audio"

    def test_invalid_input_type_raises(self):
        with pytest.raises(ValidationError):
            ProcedureRecord(
                procedure_id="p3",
                patient_cedula="3",
                transcript="x",
                input_type="invalid_type",
                triage_data=TriageDataCore(),
                confidence_score=0.0,
                created_at=_NOW,
                updated_at=_NOW,
            )


# ─── TriageRecordResponse ─────────────────────────────────────────────────────

class TestTriageRecordResponse:
    def test_basic_fields(self):
        r = TriageRecordResponse(
            procedure_id="p1",
            patient_id="123",
            preliminary_history=TriageDataCore(),
            status="pending",
        )
        assert r.procedure_id == "p1"
        assert r.status == "pending"
