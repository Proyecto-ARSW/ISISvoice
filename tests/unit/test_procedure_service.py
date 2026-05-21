"""Tests for ProcedureService."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Comment, ProcedureRecord, TriageDataCore, VitalSignsCreate
from app.services.procedure_service import ProcedureService

_NOW = datetime.now(timezone.utc)


def _make_procedure(**kwargs) -> ProcedureRecord:
    defaults = dict(
        procedure_id="proc_001",
        patient_id="12345678",
        transcript="tengo fiebre",
        input_type="text",
        preliminary_history=TriageDataCore(sintomas=["fiebre"], nivelPrioridad=3),
        confidence_score=0.75,
        created_at=_NOW,
        updated_at=_NOW,
        status="pending",
        comments=[],
        webhook_delivery="pending",
    )
    defaults.update(kwargs)
    return ProcedureRecord(**defaults)


def _make_doc(**kwargs) -> dict:
    defaults = dict(
        procedure_id="proc_001",
        patient_cedula="12345678",
        transcript="tengo fiebre",
        input_type="text",
        triage_data={"sintomas": ["fiebre"], "nivelPrioridad": 3},
        confidence_score=0.75,
        status="pending",
        comments=[],
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def svc():
    return ProcedureService()


# ─── _build_webhook_payload ───────────────────────────────────────────────────

class TestBuildWebhookPayload:
    def test_basic_fields_present(self, svc):
        proc = _make_procedure()
        payload = svc._build_webhook_payload(proc, "pending")
        assert payload["procedure_id"] == "proc_001"
        assert payload["patient_id"] == "12345678"
        assert payload["webhook_delivery"] == "pending"
        assert "preliminary_history" in payload
        assert "vital_signs" in payload
        assert "comments" in payload
        assert "created_at" in payload
        assert "updated_at" in payload

    def test_vital_signs_defaults_when_none(self, svc):
        proc = _make_procedure(vital_signs=None)
        payload = svc._build_webhook_payload(proc, "sent")
        vs = payload["vital_signs"]
        assert vs["temperature_c"] == 0
        assert vs["heart_rate_bpm"] == 0
        assert vs["oxygen_saturation_pct"] == 0

    def test_vital_signs_populated_when_present(self, svc):
        vs = VitalSignsCreate(temperature_c=37.5, heart_rate_bpm=80)
        proc = _make_procedure(vital_signs=vs)
        payload = svc._build_webhook_payload(proc, "sent")
        assert payload["vital_signs"]["temperature_c"] == 37.5
        assert payload["vital_signs"]["heart_rate_bpm"] == 80

    def test_comments_serialized(self, svc):
        comment = Comment(id="c1", comment="nota clinica", author="medico", created_at=_NOW)
        proc = _make_procedure(comments=[comment])
        payload = svc._build_webhook_payload(proc, "sent")
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["id"] == "c1"
        assert payload["comments"][0]["author"] == "medico"
        assert "created_at" in payload["comments"][0]

    def test_empty_comments(self, svc):
        proc = _make_procedure(comments=[])
        payload = svc._build_webhook_payload(proc, "sent")
        assert payload["comments"] == []

    def test_preliminary_history_fields(self, svc):
        proc = _make_procedure()
        payload = svc._build_webhook_payload(proc, "sent")
        ph = payload["preliminary_history"]
        assert "sintomas" in ph
        assert "nivelPrioridad" in ph
        assert "advertenciaIA" in ph


# ─── _deliver_webhook ─────────────────────────────────────────────────────────

class TestDeliverWebhook:
    async def test_skipped_when_no_url(self, svc):
        import app.core.settings as s_mod
        original = s_mod.settings.triage_webhook_url
        s_mod.settings.triage_webhook_url = ""
        proc = _make_procedure()
        status, msg = await svc._deliver_webhook(proc)
        s_mod.settings.triage_webhook_url = original
        assert status == "skipped"
        assert "TRIAGE_WEBHOOK_URL" in msg

    async def test_sent_on_success(self, svc):
        proc = _make_procedure()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_aclient = AsyncMock()
            mock_aclient.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_aclient)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            status, detail = await svc._deliver_webhook(proc)

        assert status == "sent"
        assert "200" in detail

    async def test_failed_on_connection_error(self, svc):
        proc = _make_procedure()
        import app.core.settings as s_mod
        original_retries = s_mod.settings.triage_webhook_max_retries
        s_mod.settings.triage_webhook_max_retries = 0

        with patch("httpx.AsyncClient") as mock_cls:
            mock_aclient = AsyncMock()
            mock_aclient.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_aclient)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            status, detail = await svc._deliver_webhook(proc)

        s_mod.settings.triage_webhook_max_retries = original_retries
        assert status == "failed"
        assert "connection refused" in detail

    async def test_includes_token_header_and_hospital_param(self, svc):
        import app.core.settings as s_mod
        orig_token = s_mod.settings.triage_webhook_token
        orig_hospital = s_mod.settings.triage_hospital_id
        orig_enfermero = s_mod.settings.triage_enfermero_id
        s_mod.settings.triage_webhook_token = "mytoken"
        s_mod.settings.triage_hospital_id = "H001"
        s_mod.settings.triage_enfermero_id = "E001"

        proc = _make_procedure()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_aclient = AsyncMock()
            mock_aclient.post = AsyncMock(return_value=mock_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_aclient)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            status, _ = await svc._deliver_webhook(proc)

        s_mod.settings.triage_webhook_token = orig_token
        s_mod.settings.triage_hospital_id = orig_hospital
        s_mod.settings.triage_enfermero_id = orig_enfermero
        assert status == "sent"

    async def test_retries_on_failure(self, svc):
        proc = _make_procedure()
        import app.core.settings as s_mod
        original_retries = s_mod.settings.triage_webhook_max_retries
        s_mod.settings.triage_webhook_max_retries = 1
        call_count = 0

        async def fail_always(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("server error")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_aclient = AsyncMock()
            mock_aclient.post = fail_always
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_aclient)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            status, detail = await svc._deliver_webhook(proc)

        s_mod.settings.triage_webhook_max_retries = original_retries
        assert status == "failed"
        assert call_count == 2  # initial + 1 retry


# ─── create_triage_record ─────────────────────────────────────────────────────

class TestCreateTriageRecord:
    async def test_creates_and_saves(self, svc):
        triage_dict = {"sintomas": ["tos"], "nivelPrioridad": 2}
        with patch("app.services.procedure_service.mongo_store.save_procedure", new_callable=AsyncMock) as mock_save, \
             patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock) as mock_update, \
             patch.object(svc, "_deliver_webhook", new_callable=AsyncMock, return_value=("sent", "HTTP 200")):
            result = await svc.create_triage_record(
                procedure_id="p001",
                patient_id="123",
                transcript="tengo tos",
                input_type="text",
                triage_data_dict=triage_dict,
                confidence_score=0.8,
            )
        mock_save.assert_called_once()
        assert result.procedure_id == "p001"
        assert result.patient_id == "123"
        assert result.input_type == "text"

    async def test_updates_webhook_status_when_changed(self, svc):
        triage_dict = {"sintomas": ["tos"], "nivelPrioridad": 2}
        with patch("app.services.procedure_service.mongo_store.save_procedure", new_callable=AsyncMock), \
             patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock) as mock_update, \
             patch.object(svc, "_deliver_webhook", new_callable=AsyncMock, return_value=("failed", "timeout")):
            result = await svc.create_triage_record(
                procedure_id="p002",
                patient_id="456",
                transcript="fiebre alta",
                input_type="text",
                triage_data_dict=triage_dict,
                confidence_score=0.7,
            )
        # pending != failed → webhook_delivery update called
        mock_update.assert_called_once()
        assert result.webhook_delivery == "failed"

    async def test_no_update_when_webhook_status_unchanged(self, svc):
        triage_dict = {"sintomas": ["tos"], "nivelPrioridad": 2}
        with patch("app.services.procedure_service.mongo_store.save_procedure", new_callable=AsyncMock), \
             patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock) as mock_update, \
             patch.object(svc, "_deliver_webhook", new_callable=AsyncMock, return_value=("pending", "skipped")):
            await svc.create_triage_record(
                procedure_id="p003",
                patient_id="789",
                transcript="nauseas",
                input_type="audio",
                triage_data_dict=triage_dict,
                confidence_score=0.6,
            )
        # pending == pending → no update
        mock_update.assert_not_called()


# ─── get_procedure ────────────────────────────────────────────────────────────

class TestGetProcedure:
    async def test_returns_procedure_record(self, svc):
        doc = _make_doc()
        with patch("app.services.procedure_service.mongo_store.get_procedure", new_callable=AsyncMock, return_value=doc):
            result = await svc.get_procedure("proc_001")
        assert result is not None
        assert result.procedure_id == "proc_001"
        assert result.patient_id == "12345678"

    async def test_returns_none_when_not_found(self, svc):
        with patch("app.services.procedure_service.mongo_store.get_procedure", new_callable=AsyncMock, return_value=None):
            result = await svc.get_procedure("ghost")
        assert result is None


# ─── get_procedures_by_cedula / get_patient_procedures ───────────────────────

class TestGetProceduresByCedula:
    async def test_returns_list(self, svc):
        doc = _make_doc()
        with patch("app.services.procedure_service.mongo_store.get_procedures_by_cedula", new_callable=AsyncMock, return_value=[doc]):
            result = await svc.get_procedures_by_cedula("12345678")
        assert len(result) == 1
        assert result[0].procedure_id == "proc_001"

    async def test_empty_list(self, svc):
        with patch("app.services.procedure_service.mongo_store.get_procedures_by_cedula", new_callable=AsyncMock, return_value=[]):
            result = await svc.get_procedures_by_cedula("nopatient")
        assert result == []

    async def test_get_patient_procedures_delegates(self, svc):
        with patch.object(svc, "get_procedures_by_cedula", new_callable=AsyncMock, return_value=[]) as mock_get:
            result = await svc.get_patient_procedures("123", limit=10)
        mock_get.assert_called_once_with("123", limit=10)
        assert result == []


# ─── add_vital_signs ──────────────────────────────────────────────────────────

class TestAddVitalSigns:
    async def test_returns_none_when_not_found(self, svc):
        vs = VitalSignsCreate(temperature_c=37.5)
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, return_value=None):
            result = await svc.add_vital_signs("ghost", vs)
        assert result is None

    async def test_updates_vital_signs_and_delivers_webhook(self, svc):
        doc = _make_doc(status="resolved", vital_signs={"temperature_c": 37.5}, webhook_delivery="sent")
        vs = VitalSignsCreate(temperature_c=37.5)
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, side_effect=[doc, doc]) as mock_update, \
             patch.object(svc, "_deliver_webhook", new_callable=AsyncMock, return_value=("sent", "HTTP 200")):
            result = await svc.add_vital_signs("proc_001", vs)
        assert result is not None
        assert mock_update.call_count == 2

    async def test_returns_procedure_when_final_doc_none(self, svc):
        doc = _make_doc(status="resolved", vital_signs={"temperature_c": 38.0}, webhook_delivery="pending")
        vs = VitalSignsCreate(temperature_c=38.0)
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, side_effect=[doc, None]), \
             patch.object(svc, "_deliver_webhook", new_callable=AsyncMock, return_value=("sent", "HTTP 200")):
            result = await svc.add_vital_signs("proc_001", vs)
        assert result is not None
        assert result.webhook_delivery == "sent"


# ─── add_comment ──────────────────────────────────────────────────────────────

class TestAddComment:
    async def test_returns_none_when_not_found(self, svc):
        with patch("app.services.procedure_service.mongo_store.add_procedure_comment", new_callable=AsyncMock, return_value=None):
            result = await svc.add_comment("ghost", "nota", "medico")
        assert result is None

    async def test_returns_updated_procedure(self, svc):
        doc = _make_doc(
            comments=[{"id": "c1", "comment": "nota clinica", "author": "medico", "created_at": _NOW}]
        )
        with patch("app.services.procedure_service.mongo_store.add_procedure_comment", new_callable=AsyncMock, return_value=doc):
            result = await svc.add_comment("proc_001", "nota clinica", "medico")
        assert result is not None
        assert len(result.comments) == 1
        assert result.comments[0].comment == "nota clinica"

    async def test_default_author_is_system(self, svc):
        doc = _make_doc(
            comments=[{"id": "c1", "comment": "nota", "author": "system", "created_at": _NOW}]
        )
        with patch("app.services.procedure_service.mongo_store.add_procedure_comment", new_callable=AsyncMock, return_value=doc):
            result = await svc.add_comment("proc_001", "nota")
        assert result.comments[0].author == "system"


# ─── list_procedures ──────────────────────────────────────────────────────────

class TestListProcedures:
    async def test_returns_list(self, svc):
        doc = _make_doc()
        with patch("app.services.procedure_service.mongo_store.list_procedures", new_callable=AsyncMock, return_value=[doc]):
            result = await svc.list_procedures(limit=10, status="pending")
        assert len(result) == 1
        assert result[0].procedure_id == "proc_001"

    async def test_empty_list(self, svc):
        with patch("app.services.procedure_service.mongo_store.list_procedures", new_callable=AsyncMock, return_value=[]):
            result = await svc.list_procedures()
        assert result == []

    async def test_no_status_filter(self, svc):
        doc = _make_doc()
        with patch("app.services.procedure_service.mongo_store.list_procedures", new_callable=AsyncMock, return_value=[doc]) as mock_list:
            await svc.list_procedures(limit=50)
        mock_list.assert_called_once_with(limit=50, status=None)


# ─── get_preliminary_history ─────────────────────────────────────────────────

class TestGetPreliminaryHistory:
    async def test_returns_dict_when_found(self, svc):
        proc = _make_procedure()
        with patch.object(svc, "get_procedure", new_callable=AsyncMock, return_value=proc):
            result = await svc.get_preliminary_history("proc_001")
        assert result is not None
        assert "sintomas" in result
        assert result["nivelPrioridad"] == 3

    async def test_returns_none_when_not_found(self, svc):
        with patch.object(svc, "get_procedure", new_callable=AsyncMock, return_value=None):
            result = await svc.get_preliminary_history("ghost")
        assert result is None


# ─── close_procedure ──────────────────────────────────────────────────────────

class TestCloseProcedure:
    async def test_closes_procedure(self, svc):
        doc = _make_doc(status="closed")
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, return_value=doc):
            result = await svc.close_procedure("proc_001")
        assert result is not None
        assert result.status == "closed"

    async def test_with_final_notes_included_in_update(self, svc):
        doc = _make_doc(status="closed")
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, return_value=doc) as mock_update:
            await svc.close_procedure("proc_001", final_notes="alta medica")
        update_dict = mock_update.call_args[0][1]
        assert "notes" in update_dict
        assert update_dict["notes"] == "alta medica"

    async def test_without_final_notes_no_notes_key(self, svc):
        doc = _make_doc(status="closed")
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, return_value=doc) as mock_update:
            await svc.close_procedure("proc_001")
        update_dict = mock_update.call_args[0][1]
        assert "notes" not in update_dict

    async def test_returns_none_when_not_found(self, svc):
        with patch("app.services.procedure_service.mongo_store.update_procedure", new_callable=AsyncMock, return_value=None):
            result = await svc.close_procedure("ghost")
        assert result is None
