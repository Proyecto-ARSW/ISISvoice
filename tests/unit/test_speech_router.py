"""Tests for speech_router endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.services.speech_service._get_model", return_value=MagicMock()):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _audio_bytes():
    return b"RIFF\x00\x00\x00\x00WAVEfmt "


def _mock_process_result(**kwargs):
    defaults = dict(
        status="success",
        transcript="tengo fiebre",
        assistant_reply="Prioridad 3",
        structured_data={"symptoms": "fiebre"},
        persistence="buffered",
        stage="triage_completed",
        model_status="ok",
    )
    defaults.update(kwargs)
    return defaults


# ─── /speech/transcribe-file ──────────────────────────────────────────────────

class TestTranscribeFile:
    def test_returns_transcription(self, client):
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="hola mundo"):
            resp = client.post(
                "/speech/transcribe-file",
                files={"file": ("test.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transcription"] == "hola mundo"
        assert data["success"] is True
        assert data["filename"] == "test.wav"

    def test_empty_file_returns_400(self, client):
        resp = client.post(
            "/speech/transcribe-file",
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_transcription_exception_returns_400(self, client):
        with patch("app.routers.speech_router.transcribe_audio_bytes", side_effect=Exception("codec error")):
            resp = client.post(
                "/speech/transcribe-file",
                files={"file": ("test.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 400
        assert "codec error" in resp.json()["detail"]


# ─── /speech/clinical/start ───────────────────────────────────────────────────

class TestClinicalStart:
    def test_starts_new_session_without_id(self, client):
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock):
            resp = client.post("/speech/clinical/start", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "session-started"
        assert "session_id" in data
        assert data["model_status"] == "ok"

    def test_reuses_provided_session_id(self, client):
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock):
            resp = client.post("/speech/clinical/start", json={"session_id": "my-sess-123"})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "my-sess-123"

    def test_clinical_data_all_null(self, client):
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock):
            resp = client.post("/speech/clinical/start", json={})
        data = resp.json()
        cd = data["clinical_data"]
        assert cd["symptoms"] is None
        assert cd["pregnancy"] is None


# ─── /speech/clinical/audio ───────────────────────────────────────────────────

class TestClinicalAudio:
    def test_processes_audio_successfully(self, client):
        mock_result = _mock_process_result(persistence="persisted")
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="tengo fiebre"), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/speech/clinical/audio",
                data={"session_id": "sess_001"},
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["session_id"] == "sess_001"
        assert data["transcript"] == "tengo fiebre"
        assert data["model_status"] == "ok"

    def test_empty_file_returns_400(self, client):
        resp = client.post(
            "/speech/clinical/audio",
            data={"session_id": "sess_001"},
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert resp.status_code == 400

    def test_transcription_error_prefix_returns_400(self, client):
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="[Error: codec failed]"):
            resp = client.post(
                "/speech/clinical/audio",
                data={"session_id": "sess_001"},
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 400
        assert "codec failed" in resp.json()["detail"]


# ─── /speech/ia/analyze ───────────────────────────────────────────────────────

class TestIaAnalyze:
    def test_analyzes_text_successfully(self, client):
        mock_result = _mock_process_result()
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/speech/ia/analyze", json={"transcript": "tengo dolor de cabeza"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["stage"] == "triage_completed"

    def test_empty_transcript_returns_400(self, client):
        resp = client.post("/speech/ia/analyze", json={"transcript": ""})
        assert resp.status_code == 400
        assert "transcript is required" in resp.json()["detail"]

    def test_whitespace_transcript_returns_400(self, client):
        resp = client.post("/speech/ia/analyze", json={"transcript": "   "})
        assert resp.status_code == 400

    def test_uses_provided_session_id(self, client):
        mock_result = _mock_process_result()
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/speech/ia/analyze", json={"transcript": "fiebre", "session_id": "sess_abc"})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess_abc"

    def test_generates_session_id_when_none(self, client):
        mock_result = _mock_process_result()
        with patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/speech/ia/analyze", json={"transcript": "fiebre"})
        assert resp.status_code == 200
        assert resp.json()["session_id"]  # non-empty generated UUID


# ─── /speech/flow/audio ───────────────────────────────────────────────────────

class TestFlowAudio:
    def test_returns_503_when_not_persisted(self, client):
        mock_result = _mock_process_result(persistence="buffered")
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="fiebre"), \
             patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/speech/flow/audio",
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 503
        assert "MongoDB" in resp.json()["detail"] or "no disponible" in resp.json()["detail"]

    def test_returns_200_when_persisted(self, client):
        mock_result = _mock_process_result(persistence="persisted")
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="fiebre"), \
             patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/speech/flow/audio",
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["persistence"] == "persisted"
        assert data["model_status"] == "ok"

    def test_empty_file_returns_400(self, client):
        resp = client.post(
            "/speech/flow/audio",
            files={"file": ("empty.wav", b"", "audio/wav")},
        )
        assert resp.status_code == 400

    def test_transcription_error_returns_400(self, client):
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="[Error: format not supported]"):
            resp = client.post(
                "/speech/flow/audio",
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 400

    def test_uses_provided_session_id(self, client):
        mock_result = _mock_process_result(persistence="persisted")
        with patch("app.routers.speech_router.transcribe_audio_bytes", return_value="ok"), \
             patch("app.routers.speech_router.clinical_conversation_service.ensure_session", new_callable=AsyncMock), \
             patch("app.routers.speech_router.clinical_conversation_service.process_user_message", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/speech/flow/audio",
                data={"session_id": "sess_flow"},
                files={"file": ("audio.wav", _audio_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess_flow"


# ─── /speech/clinical/finalize/{session_id} ──────────────────────────────────

class TestClinicalFinalize:
    def test_finalizes_session_successfully(self, client):
        mock_result = {
            "status": "completed",
            "session_id": "sess_001",
            "final_clinical_history": {"summary": "Sintomas: fiebre.", "clinical_history": {}},
            "persistence": "persisted",
        }
        with patch("app.routers.speech_router.clinical_conversation_service.finalize_session", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/speech/clinical/finalize/sess_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "session-completed"
        assert data["session_id"] == "sess_001"
        assert data["persistence"] == "persisted"
        assert data["model_status"] == "ok"

    def test_finalize_returns_final_history(self, client):
        mock_result = {
            "status": "completed",
            "session_id": "sess_002",
            "final_clinical_history": {
                "summary": "Sintomas: tos.",
                "clinical_history": {"symptoms": "tos"},
                "engine": "deterministic-rules",
            },
            "persistence": "buffered",
        }
        with patch("app.routers.speech_router.clinical_conversation_service.finalize_session", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post("/speech/clinical/finalize/sess_002")
        data = resp.json()
        assert data["persistence"] == "buffered"
        assert "summary" in data["final_clinical_history"]


# ─── /speech/health ───────────────────────────────────────────────────────────

class TestSpeechHealth:
    def test_healthy_when_mongo_status_up(self, client):
        health_data = {
            "mongo": {"status": "up", "mongodb": "connected"},
            "clinical_engine": {"status": "up", "type": "deterministic-rules"},
        }
        with patch("app.routers.speech_router.clinical_conversation_service.health", new_callable=AsyncMock, return_value=health_data):
            resp = client.get("/speech/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "speech-service"
        assert isinstance(data["endpoints"], list)
        assert len(data["endpoints"]) > 0

    def test_degraded_when_mongo_not_up(self, client):
        health_data = {
            "mongo": {"status": "degraded", "error": "timeout"},
            "clinical_engine": {"status": "up"},
        }
        with patch("app.routers.speech_router.clinical_conversation_service.health", new_callable=AsyncMock, return_value=health_data):
            resp = client.get("/speech/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"

    def test_degraded_when_mongo_missing(self, client):
        health_data = {
            "clinical_engine": {"status": "up"},
        }
        with patch("app.routers.speech_router.clinical_conversation_service.health", new_callable=AsyncMock, return_value=health_data):
            resp = client.get("/speech/health")
        assert resp.json()["status"] == "degraded"
