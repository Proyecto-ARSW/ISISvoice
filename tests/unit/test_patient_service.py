"""Tests for PatientService."""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models import PatientCreate, PatientUpdate, PatientResponse
from app.services.patient_service import PatientService

_M = "app.services.patient_service.mongo_store"
_NOW = datetime.now(timezone.utc)
_DOB = date(1990, 1, 1)


def _make_patient_doc(**kwargs) -> dict:
    defaults = dict(
        cedula="12345678",
        nombres="Juan",
        apellidos="Perez",
        fecha_nacimiento=_DOB,
        eps="Sura",
        genero="M",
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    return defaults


def _make_patient_create(**kwargs) -> PatientCreate:
    defaults = dict(
        cedula="12345678",
        nombres="Juan",
        apellidos="Perez",
        fecha_nacimiento=_DOB,
        eps="Sura",
        genero="M",
    )
    defaults.update(kwargs)
    return PatientCreate(**defaults)


@pytest.fixture
def svc():
    return PatientService()


# ─── create_patient ───────────────────────────────────────────────────────────

class TestCreatePatient:
    async def test_creates_and_returns_patient(self, svc):
        patient_data = _make_patient_create()
        doc = _make_patient_doc()

        with patch(f"{_M}.save_patient", new_callable=AsyncMock, return_value=doc):
            result = await svc.create_patient(patient_data)

        assert isinstance(result, PatientResponse)
        assert result.cedula == "12345678"

    async def test_created_at_timestamp_set(self, svc):
        patient_data = _make_patient_create(cedula="87654321", nombres="Maria", apellidos="Lopez", genero="F")
        doc = _make_patient_doc(cedula="87654321", nombres="Maria", apellidos="Lopez", genero="F")

        with patch(f"{_M}.save_patient", new_callable=AsyncMock, return_value=doc):
            result = await svc.create_patient(patient_data)

        assert result.created_at is not None


# ─── get_patient ──────────────────────────────────────────────────────────────

class TestGetPatient:
    async def test_returns_patient_when_found(self, svc):
        doc = _make_patient_doc()
        with patch(f"{_M}.get_patient", new_callable=AsyncMock, return_value=doc):
            result = await svc.get_patient("12345678")
        assert isinstance(result, PatientResponse)
        assert result.cedula == "12345678"

    async def test_returns_none_when_not_found(self, svc):
        with patch(f"{_M}.get_patient", new_callable=AsyncMock, return_value=None):
            result = await svc.get_patient("nonexistent")
        assert result is None


# ─── update_patient ───────────────────────────────────────────────────────────

class TestUpdatePatient:
    async def test_returns_updated_patient(self, svc):
        doc = _make_patient_doc(nombres="Juan Carlos")
        update = PatientUpdate(nombres="Juan Carlos")
        with patch(f"{_M}.update_patient", new_callable=AsyncMock, return_value=doc):
            result = await svc.update_patient("12345678", update)
        assert isinstance(result, PatientResponse)
        assert result.nombres == "Juan Carlos"

    async def test_returns_none_when_not_found(self, svc):
        update = PatientUpdate(nombres="Nuevo")
        with patch(f"{_M}.update_patient", new_callable=AsyncMock, return_value=None):
            result = await svc.update_patient("nonexistent", update)
        assert result is None


# ─── list_patients ────────────────────────────────────────────────────────────

class TestListPatients:
    async def test_returns_list(self, svc):
        docs = [_make_patient_doc(cedula=str(i)) for i in range(3)]
        with patch(f"{_M}.list_patients", new_callable=AsyncMock, return_value=docs):
            result = await svc.list_patients()
        assert len(result) == 3
        assert all(isinstance(p, PatientResponse) for p in result)

    async def test_empty_list(self, svc):
        with patch(f"{_M}.list_patients", new_callable=AsyncMock, return_value=[]):
            result = await svc.list_patients()
        assert result == []

    async def test_passes_limit_and_skip(self, svc):
        with patch(f"{_M}.list_patients", new_callable=AsyncMock, return_value=[]) as mock_list:
            await svc.list_patients(limit=10, skip=5)
        mock_list.assert_called_once_with(limit=10, skip=5)


# ─── patient_exists ───────────────────────────────────────────────────────────

class TestPatientExists:
    async def test_returns_true_when_found(self, svc):
        doc = _make_patient_doc()
        with patch(f"{_M}.get_patient", new_callable=AsyncMock, return_value=doc):
            assert await svc.patient_exists("12345678") is True

    async def test_returns_false_when_not_found(self, svc):
        with patch(f"{_M}.get_patient", new_callable=AsyncMock, return_value=None):
            assert await svc.patient_exists("nonexistent") is False
