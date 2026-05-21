"""Tests for triage router endpoints."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import ProcedureRecord, TriageDataCore

_NOW = datetime.now(timezone.utc)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_procedure(
    patient_id: str = "12345678",
    procedure_id: str = "proc_001",
    status: str = "pending",
) -> ProcedureRecord:
    return ProcedureRecord(
        procedure_id=procedure_id,
        patient_cedula=patient_id,
        transcript="tengo fiebre",
        input_type="text",
        triage_data=TriageDataCore(sintomas=["fiebre"], nivelPrioridad=3),
        confidence_score=0.75,
        created_at=_NOW,
        updated_at=_NOW,
        status=status,
    )


def _default_triage() -> TriageDataCore:
    return TriageDataCore(
        sintomas=["fiebre"],
        posiblesCausas=["dengue"],
        nivelPrioridad=3,
        comentario="fiebre desde ayer",
        comentariosIA="IA: prioridad media",
    )


@pytest.fixture
def client(patch_jwt_secret):
    from app.main import app
    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.services.speech_service._get_model", return_value=MagicMock()):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ─── POST /api/v1/triage/symptoms/text ───────────────────────────────────────

class TestIngestSymptomsText:
    def test_valid_request_returns_200(self, client, make_token):
        with patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.75), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_001"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3: atención en 2 horas"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/text",
                json={"text_input": "tengo fiebre y dolor de cabeza desde ayer"},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200
        data = r.json()
        assert "procedure_id" in data
        assert "recommendation" in data
        assert "patient_id" in data
        assert data["status"] == "pending"

    def test_no_auth_returns_401(self, client):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "tengo fiebre"},
        )
        assert r.status_code == 401

    def test_wrong_role_medico_returns_403(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "tengo fiebre"},
            headers=make_token("MEDICO"),
        )
        assert r.status_code == 403

    def test_wrong_role_enfermero_returns_403(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "tengo fiebre"},
            headers=make_token("ENFERMERO"),
        )
        assert r.status_code == 403

    def test_missing_text_field_returns_422(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"wrong_field": "valor"},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 422

    def test_alternative_field_symptoms_accepted(self, client, make_token):
        with patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.5), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_002"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/text",
                json={"symptoms": "tengo fiebre"},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200

    def test_alternative_field_textinput_camelcase(self, client, make_token):
        with patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.5), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_003"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/text",
                json={"textInput": "tengo fiebre alta"},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200

    def test_expired_token_returns_401(self, client, expired_token):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "fiebre"},
            headers=expired_token,
        )
        assert r.status_code == 401

    def test_invalid_token_returns_401(self, client):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "fiebre"},
            headers={"Authorization": "Bearer not.a.real.token"},
        )
        assert r.status_code == 401

    def test_whitespace_only_text_returns_400(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/text",
            json={"text_input": "   "},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 400
        assert "text_input" in r.json()["detail"]


# ─── POST /api/v1/triage/symptoms/audio/base64 ───────────────────────────────

class TestIngestSymptomsAudioBase64:
    def test_invalid_base64_returns_400(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/audio/base64",
            json={"audio_base64": "not_valid_base64!!!@#$"},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 400

    def test_transcript_too_short_returns_400(self, client, make_token):
        valid_b64 = base64.b64encode(b"fake_audio").decode()
        with patch("app.routers.triage_router.transcribe_audio_bytes", return_value="hi"):
            r = client.post(
                "/api/v1/triage/symptoms/audio/base64",
                json={"audio_base64": valid_b64},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 400

    def test_empty_transcript_returns_400(self, client, make_token):
        valid_b64 = base64.b64encode(b"bytes").decode()
        with patch("app.routers.triage_router.transcribe_audio_bytes", return_value=""):
            r = client.post(
                "/api/v1/triage/symptoms/audio/base64",
                json={"audio_base64": valid_b64},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 400

    def test_valid_audio_returns_200(self, client, make_token):
        valid_b64 = base64.b64encode(b"fake_audio_content_bytes").decode()
        with patch("app.routers.triage_router.transcribe_audio_bytes",
                   return_value="tengo fiebre y mucho dolor de cabeza severo"), \
             patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.75), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_audio_001"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/audio/base64",
                json={"audio_base64": valid_b64, "file_name": "audio.wav"},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200

    def test_data_uri_prefix_stripped(self, client, make_token):
        raw = base64.b64encode(b"fake_audio_content").decode()
        data_uri = f"data:audio/wav;base64,{raw}"
        with patch("app.routers.triage_router.transcribe_audio_bytes",
                   return_value="tengo mucho dolor de cabeza y fiebre alta"), \
             patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.7), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_uri_001"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/audio/base64",
                json={"audio_base64": data_uri},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200

    def test_no_auth_returns_401(self, client):
        valid_b64 = base64.b64encode(b"audio").decode()
        r = client.post(
            "/api/v1/triage/symptoms/audio/base64",
            json={"audio_base64": valid_b64},
        )
        assert r.status_code == 401

    def test_missing_audio_field_returns_422(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/audio/base64",
            json={"wrong_field": "value"},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 422

    def test_camelcase_audio_field_accepted(self, client, make_token):
        valid_b64 = base64.b64encode(b"fake_audio_content_2").decode()
        with patch("app.routers.triage_router.transcribe_audio_bytes",
                   return_value="tengo fiebre muy alta y vomito"), \
             patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.6), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_cc_001"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/audio/base64",
                json={"audioBase64": valid_b64},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200



# ─── GET /api/v1/triage/record/{id}/preliminary-history ─────────────────────

class TestGetPreliminaryHistory:
    def test_existing_own_procedure_returns_200(self, client, make_token):
        proc = _make_procedure(patient_id="12345678")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.get(
                f"/api/v1/triage/record/{proc.procedure_id}/preliminary-history",
                headers=make_token("PACIENTE", "12345678"),
            )
        assert r.status_code == 200
        data = r.json()
        assert "nivelPrioridad" in data
        assert "sintomas" in data

    def test_not_found_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=None):
            r = client.get(
                "/api/v1/triage/record/nonexistent_id/preliminary-history",
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 404

    def test_paciente_accessing_other_patient_returns_403(self, client, make_token):
        proc = _make_procedure(patient_id="99999999")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.get(
                f"/api/v1/triage/record/{proc.procedure_id}/preliminary-history",
                headers=make_token("PACIENTE", "11111111"),
            )
        assert r.status_code == 403

    def test_medico_can_access_any_patient_record(self, client, make_token):
        proc = _make_procedure(patient_id="99999999")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.get(
                f"/api/v1/triage/record/{proc.procedure_id}/preliminary-history",
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 200

    def test_no_auth_returns_401(self, client):
        r = client.get("/api/v1/triage/record/proc_001/preliminary-history")
        assert r.status_code == 401


# ─── GET /api/v1/triage/procedure/{id} ───────────────────────────────────────

class TestGetProcedure:
    def test_own_procedure_returns_200(self, client, make_token):
        proc = _make_procedure(patient_id="12345678")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.get(
                f"/api/v1/triage/procedure/{proc.procedure_id}",
                headers=make_token("PACIENTE", "12345678"),
            )
        assert r.status_code == 200
        data = r.json()
        assert data["procedure_id"] == "proc_001"

    def test_not_found_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=None):
            r = client.get(
                "/api/v1/triage/procedure/nonexistent",
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 404

    def test_other_patient_returns_403(self, client, make_token):
        proc = _make_procedure(patient_id="owner_123")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.get(
                f"/api/v1/triage/procedure/{proc.procedure_id}",
                headers=make_token("PACIENTE", "other_user"),
            )
        assert r.status_code == 403


# ─── GET /api/v1/triage/procedures/my ────────────────────────────────────────

class TestGetMyProcedures:
    def test_returns_patient_list(self, client, make_token):
        procs = [_make_procedure("12345678", f"proc_{i}") for i in range(3)]
        with patch("app.routers.triage_router.procedure_service.get_patient_procedures",
                   new_callable=AsyncMock, return_value=procs):
            r = client.get(
                "/api/v1/triage/procedures/my",
                headers=make_token("PACIENTE", "12345678"),
            )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 3

    def test_empty_list_ok(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.get_patient_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get(
                "/api/v1/triage/procedures/my",
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_wrong_role_returns_403(self, client, make_token):
        r = client.get("/api/v1/triage/procedures/my", headers=make_token("MEDICO"))
        assert r.status_code == 403

    def test_no_auth_returns_401(self, client):
        r = client.get("/api/v1/triage/procedures/my")
        assert r.status_code == 401

    def test_legacy_me_endpoint_works(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.get_patient_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get(
                "/api/v1/triage/procedures/me",
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200


# ─── GET /api/v1/triage/records ──────────────────────────────────────────────

class TestListTriageRecords:
    def test_medico_can_list(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[_make_procedure()]):
            r = client.get("/api/v1/triage/records", headers=make_token("MEDICO"))
        assert r.status_code == 200
        assert "items" in r.json()

    def test_enfermero_can_list(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/v1/triage/records", headers=make_token("ENFERMERO"))
        assert r.status_code == 200

    def test_admin_can_list(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/v1/triage/records", headers=make_token("ADMIN"))
        assert r.status_code == 200

    def test_paciente_cannot_list(self, client, make_token):
        r = client.get("/api/v1/triage/records", headers=make_token("PACIENTE"))
        assert r.status_code == 403

    def test_invalid_status_returns_400(self, client, make_token):
        r = client.get("/api/v1/triage/records?status=invalid_status", headers=make_token("MEDICO"))
        assert r.status_code == 400

    def test_valid_status_pending(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/v1/triage/records?status=pending", headers=make_token("MEDICO"))
        assert r.status_code == 200

    def test_valid_status_resolved(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/v1/triage/records?status=resolved", headers=make_token("MEDICO"))
        assert r.status_code == 200

    def test_status_all_returns_all(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.list_procedures",
                   new_callable=AsyncMock, return_value=[]) as mock_list:
            r = client.get("/api/v1/triage/records?status=all", headers=make_token("MEDICO"))
            # "all" maps to None (no filter)
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args
            assert call_kwargs.kwargs.get("status") is None or (
                len(call_kwargs.args) >= 2 and call_kwargs.args[1] is None
            )
        assert r.status_code == 200

    def test_no_auth_returns_401(self, client):
        r = client.get("/api/v1/triage/records")
        assert r.status_code == 401


# ─── PUT /api/v1/triage/record/{id}/vital-signs ──────────────────────────────

class TestUpdateVitalSigns:
    def test_medico_can_update(self, client, make_token):
        proc = _make_procedure()
        with patch("app.routers.triage_router.procedure_service.add_vital_signs",
                   new_callable=AsyncMock, return_value=proc):
            r = client.put(
                f"/api/v1/triage/record/{proc.procedure_id}/vital-signs",
                json={"temperature_c": 38.5, "heart_rate_bpm": 90},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 200

    def test_enfermero_can_update(self, client, make_token):
        proc = _make_procedure()
        with patch("app.routers.triage_router.procedure_service.add_vital_signs",
                   new_callable=AsyncMock, return_value=proc):
            r = client.put(
                f"/api/v1/triage/record/{proc.procedure_id}/vital-signs",
                json={"temperature_c": 37.0},
                headers=make_token("ENFERMERO"),
            )
        assert r.status_code == 200

    def test_not_found_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.add_vital_signs",
                   new_callable=AsyncMock, return_value=None):
            r = client.put(
                "/api/v1/triage/record/nonexistent/vital-signs",
                json={"temperature_c": 37.0},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 404

    def test_paciente_own_procedure_allowed(self, client, make_token):
        proc = _make_procedure(patient_id="12345678")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc), \
             patch("app.routers.triage_router.procedure_service.add_vital_signs",
                   new_callable=AsyncMock, return_value=proc):
            r = client.put(
                f"/api/v1/triage/record/{proc.procedure_id}/vital-signs",
                json={"temperature_c": 37.5},
                headers=make_token("PACIENTE", "12345678"),
            )
        assert r.status_code == 200

    def test_paciente_other_procedure_returns_403(self, client, make_token):
        proc = _make_procedure(patient_id="owner_id")
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.put(
                f"/api/v1/triage/record/{proc.procedure_id}/vital-signs",
                json={"temperature_c": 37.5},
                headers=make_token("PACIENTE", "other_id"),
            )
        assert r.status_code == 403

    def test_paciente_nonexistent_procedure_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.get_procedure",
                   new_callable=AsyncMock, return_value=None):
            r = client.put(
                "/api/v1/triage/record/nonexistent_proc/vital-signs",
                json={"temperature_c": 37.5},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 404


# ─── POST /api/v1/triage/record/{id}/comment ─────────────────────────────────

class TestAddComment:
    def test_medico_can_add_comment(self, client, make_token):
        proc = _make_procedure()
        with patch("app.routers.triage_router.procedure_service.add_comment",
                   new_callable=AsyncMock, return_value=proc):
            r = client.post(
                f"/api/v1/triage/record/{proc.procedure_id}/comment",
                json={"comment": "paciente estable, monitorear"},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 200

    def test_enfermero_can_add_comment(self, client, make_token):
        proc = _make_procedure()
        with patch("app.routers.triage_router.procedure_service.add_comment",
                   new_callable=AsyncMock, return_value=proc):
            r = client.post(
                f"/api/v1/triage/record/{proc.procedure_id}/comment",
                json={"comment": "signos vitales normales"},
                headers=make_token("ENFERMERO"),
            )
        assert r.status_code == 200

    def test_paciente_cannot_add_comment(self, client, make_token):
        r = client.post(
            "/api/v1/triage/record/proc_001/comment",
            json={"comment": "comentario"},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 403

    def test_not_found_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.add_comment",
                   new_callable=AsyncMock, return_value=None):
            r = client.post(
                "/api/v1/triage/record/nonexistent/comment",
                json={"comment": "nota"},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 404

    def test_no_auth_returns_401(self, client):
        r = client.post(
            "/api/v1/triage/record/proc_001/comment",
            json={"comment": "nota"},
        )
        assert r.status_code == 401


# ─── POST /api/v1/triage/record/{id}/close ───────────────────────────────────

class TestCloseProcedure:
    def test_medico_can_close(self, client, make_token):
        proc = _make_procedure(status="closed")
        with patch("app.routers.triage_router.procedure_service.close_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.post(
                f"/api/v1/triage/record/{proc.procedure_id}/close",
                json={},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 200

    def test_enfermero_can_close(self, client, make_token):
        proc = _make_procedure(status="closed")
        with patch("app.routers.triage_router.procedure_service.close_procedure",
                   new_callable=AsyncMock, return_value=proc):
            r = client.post(
                f"/api/v1/triage/record/{proc.procedure_id}/close",
                json={"close_reason": "alta medica"},
                headers=make_token("ENFERMERO"),
            )
        assert r.status_code == 200

    def test_paciente_cannot_close(self, client, make_token):
        r = client.post(
            "/api/v1/triage/record/proc_001/close",
            json={},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 403

    def test_not_found_returns_404(self, client, make_token):
        with patch("app.routers.triage_router.procedure_service.close_procedure",
                   new_callable=AsyncMock, return_value=None):
            r = client.post(
                "/api/v1/triage/record/nonexistent/close",
                json={},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 404

    def test_close_with_reason(self, client, make_token):
        proc = _make_procedure(status="closed")
        with patch("app.routers.triage_router.procedure_service.close_procedure",
                   new_callable=AsyncMock, return_value=proc) as mock_close:
            r = client.post(
                f"/api/v1/triage/record/{proc.procedure_id}/close",
                json={"close_reason": "paciente dado de alta"},
                headers=make_token("MEDICO"),
            )
        assert r.status_code == 200
        mock_close.assert_called_once()
        call_kwargs = mock_close.call_args
        assert "paciente dado de alta" in str(call_kwargs)


# ─── POST /api/v1/triage/symptoms/audio (multipart) ─────────────────────────

class TestIngestSymptomsAudioMultipart:
    def _audio_bytes(self):
        return b"RIFF\x00\x00\x00\x00WAVEfmt "

    def test_valid_audio_returns_200(self, client, make_token):
        with patch("app.routers.triage_router.transcribe_audio_bytes",
                   return_value="tengo fiebre muy alta y dolor de cabeza"), \
             patch("app.routers.triage_router.triage_extraction_service.extract_preliminary_history",
                   new_callable=AsyncMock, return_value=_default_triage()), \
             patch("app.routers.triage_router.triage_extraction_service.get_confidence_score",
                   return_value=0.75), \
             patch("app.routers.triage_router.triage_extraction_service.generate_procedure_id",
                   return_value="proc_mp_001"), \
             patch("app.routers.triage_router.triage_extraction_service.build_recommendation",
                   return_value="N3"), \
             patch("app.routers.triage_router.procedure_service.create_triage_record",
                   new_callable=AsyncMock, return_value=_make_procedure()):
            r = client.post(
                "/api/v1/triage/symptoms/audio",
                files={"audio_file": ("audio.wav", self._audio_bytes(), "audio/wav")},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 200
        assert "procedure_id" in r.json()

    def test_empty_file_returns_400(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/audio",
            files={"audio_file": ("empty.wav", b"", "audio/wav")},
            headers=make_token("PACIENTE"),
        )
        assert r.status_code == 400
        assert "vacio" in r.json()["detail"].lower()

    def test_short_transcript_returns_400(self, client, make_token):
        with patch("app.routers.triage_router.transcribe_audio_bytes", return_value="hi"):
            r = client.post(
                "/api/v1/triage/symptoms/audio",
                files={"audio_file": ("audio.wav", self._audio_bytes(), "audio/wav")},
                headers=make_token("PACIENTE"),
            )
        assert r.status_code == 400

    def test_no_auth_returns_401(self, client):
        r = client.post(
            "/api/v1/triage/symptoms/audio",
            files={"audio_file": ("audio.wav", self._audio_bytes(), "audio/wav")},
        )
        assert r.status_code == 401

    def test_wrong_role_returns_403(self, client, make_token):
        r = client.post(
            "/api/v1/triage/symptoms/audio",
            files={"audio_file": ("audio.wav", self._audio_bytes(), "audio/wav")},
            headers=make_token("MEDICO"),
        )
        assert r.status_code == 403
