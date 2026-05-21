"""Tests for ClinicalConversationService."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.clinical_conversation_service import ClinicalConversationService

# Shortcut for patching methods that don't exist on MongoStore singleton
_M = "app.services.clinical_conversation_service.mongo_store"


def _mock_store_method(method: str, **kwargs):
    """Patch a method on the mongo_store singleton, creating it if needed."""
    return patch(f"{_M}.{method}", new_callable=AsyncMock, create=True, **kwargs)


@pytest.fixture
def svc():
    return ClinicalConversationService()


# ─── _clean_text ──────────────────────────────────────────────────────────────

class TestCleanText:
    def test_none_returns_empty(self, svc):
        assert svc._clean_text(None) == ""

    def test_strips_whitespace(self, svc):
        assert svc._clean_text("  hola  ") == "hola"

    def test_none_string_variants_return_empty(self, svc):
        for val in ("none", "None", "null", "undefined", "nan", "NaN"):
            assert svc._clean_text(val) == "", f"Expected '' for '{val}'"

    def test_normal_text_unchanged(self, svc):
        assert svc._clean_text("fiebre alta") == "fiebre alta"

    def test_numeric_value_becomes_string(self, svc):
        assert svc._clean_text(42) == "42"


# ─── _normalize_structured_data ───────────────────────────────────────────────

class TestNormalizeStructuredData:
    def test_populates_known_fields(self, svc):
        data = {"symptoms": "fiebre", "current_medications": "ibuprofeno"}
        result = svc._normalize_structured_data(data)
        assert result["symptoms"] == "fiebre"
        assert result["current_medications"] == "ibuprofeno"

    def test_missing_fields_become_none(self, svc):
        result = svc._normalize_structured_data({"symptoms": "dolor"})
        assert result["pregnancy"] is None
        assert result["recent_trauma"] is None
        assert result["possible_justification"] is None

    def test_null_string_values_become_none(self, svc):
        data = {"symptoms": "none", "current_medications": "null"}
        result = svc._normalize_structured_data(data)
        assert result["symptoms"] is None
        assert result["current_medications"] is None

    def test_empty_dict_all_none(self, svc):
        result = svc._normalize_structured_data({})
        for key in svc.OUTPUT_FIELD_ORDER:
            assert result[key] is None

    def test_output_field_order_preserved(self, svc):
        data = {k: f"val_{k}" for k in svc.OUTPUT_FIELD_ORDER}
        result = svc._normalize_structured_data(data)
        assert list(result.keys()) == list(svc.OUTPUT_FIELD_ORDER)


# ─── _next_stage_and_question ─────────────────────────────────────────────────

class TestNextStageAndQuestion:
    def test_no_symptoms_returns_intake_with_question(self, svc):
        stage, question = svc._next_stage_and_question({})
        assert stage == "intake"
        assert len(question) > 0

    def test_none_symptoms_returns_intake(self, svc):
        stage, question = svc._next_stage_and_question({"symptoms": None})
        assert stage == "intake"

    def test_empty_string_symptoms_returns_intake(self, svc):
        stage, question = svc._next_stage_and_question({"symptoms": ""})
        assert stage == "intake"

    def test_has_symptoms_returns_ready_to_finalize(self, svc):
        stage, question = svc._next_stage_and_question({"symptoms": "fiebre"})
        assert stage == "ready_to_finalize"
        assert question == ""


# ─── _build_summary ───────────────────────────────────────────────────────────

class TestBuildSummary:
    def test_builds_summary_with_full_data(self, svc):
        data = {
            "symptoms": "fiebre alta",
            "recent_trauma": "caida",
            "current_medications": "acetaminofen",
            "pregnancy": "no",
            "possible_justification": "gripe",
        }
        summary = svc._build_summary(data)
        assert "fiebre alta" in summary
        assert "caida" in summary
        assert "acetaminofen" in summary
        assert "gripe" in summary

    def test_builds_summary_with_empty_data(self, svc):
        summary = svc._build_summary({})
        assert "sin sintomas registrados" in summary
        assert "sin dato de trauma" in summary
        assert "sin dato de medicamentos" in summary
        assert "sin dato de embarazo" in summary
        assert "sin justificante reportado" in summary


# ─── _mongo_with_retries ──────────────────────────────────────────────────────

class TestMongoWithRetries:
    async def test_returns_result_on_success(self, svc):
        result = await svc._mongo_with_retries(lambda: AsyncMock(return_value="ok")())
        assert result == "ok"

    async def test_raises_last_error_after_retries(self, svc):
        import app.core.settings as s_mod
        original = s_mod.settings.mongo_max_retries
        s_mod.settings.mongo_max_retries = 0

        async def always_fail():
            raise RuntimeError("DB down")

        with pytest.raises(RuntimeError, match="DB down"):
            await svc._mongo_with_retries(always_fail)

        s_mod.settings.mongo_max_retries = original

    async def test_retries_before_raising(self, svc):
        import app.core.settings as s_mod
        original = s_mod.settings.mongo_max_retries
        s_mod.settings.mongo_max_retries = 2
        call_count = 0

        async def counting_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError):
                await svc._mongo_with_retries(counting_fail)

        s_mod.settings.mongo_max_retries = original
        assert call_count == 3  # initial + 2 retries


# ─── _append_user_message / _append_assistant_message ────────────────────────

class TestAppendMessages:
    async def test_append_user_persisted(self, svc):
        with _mock_store_method("ensure_session"), \
             _mock_store_method("append_message"):
            status = await svc._append_user_message("sess_001", "tengo fiebre")
        assert status == "persisted"
        assert svc._local_history["sess_001"][-1]["content"] == "tengo fiebre"

    async def test_append_user_buffered_on_error(self, svc):
        with _mock_store_method("ensure_session", side_effect=Exception("DB error")):
            status = await svc._append_user_message("sess_002", "dolor cabeza")
        assert status == "buffered"
        assert svc._local_history["sess_002"][-1]["content"] == "dolor cabeza"

    async def test_append_assistant_persisted(self, svc):
        with _mock_store_method("append_message"):
            status = await svc._append_assistant_message("sess_001", "Prioridad 3")
        assert status == "persisted"

    async def test_append_assistant_buffered_on_error(self, svc):
        with _mock_store_method("append_message", side_effect=Exception("DB error")):
            status = await svc._append_assistant_message("sess_002", "ok")
        assert status == "buffered"


# ─── _load_history ────────────────────────────────────────────────────────────

class TestLoadHistory:
    async def test_returns_from_mongo(self, svc):
        history = [{"role": "user", "content": "fiebre"}]
        with _mock_store_method("get_history", return_value=history):
            result, source = await svc._load_history("sess_001")
        assert result == history
        assert source == "persisted"

    async def test_falls_back_to_local_on_error(self, svc):
        svc._local_history["sess_local"] = [{"role": "user", "content": "nauseas"}]
        with _mock_store_method("get_history", side_effect=Exception("DB")):
            result, source = await svc._load_history("sess_local")
        assert source == "buffered"
        assert result[0]["content"] == "nauseas"

    async def test_empty_mongo_history_falls_back_to_local(self, svc):
        svc._local_history["sess_x"] = [{"role": "user", "content": "tos"}]
        with _mock_store_method("get_history", return_value=[]):
            result, source = await svc._load_history("sess_x")
        assert source == "buffered"


# ─── ensure_session ───────────────────────────────────────────────────────────

class TestEnsureSession:
    async def test_persists_to_mongo_successfully(self, svc):
        with _mock_store_method("ensure_session") as mock_ensure:
            await svc.ensure_session("sess_001")
        mock_ensure.assert_called_once()

    async def test_falls_back_to_local_on_error(self, svc):
        with _mock_store_method("ensure_session", side_effect=Exception("DB down")):
            await svc.ensure_session("sess_fail")
        assert "sess_fail" in svc._local_history
        assert "sess_fail" in svc._local_structured


# ─── process_user_message ─────────────────────────────────────────────────────

class TestProcessUserMessage:
    async def test_empty_transcript_returns_no_speech(self, svc):
        with _mock_store_method("ensure_session"):
            result = await svc.process_user_message("sess_001", "")
        assert result["status"] == "no-speech"
        assert result["transcript"] == ""
        assert result["structured_data"] == {}

    async def test_whitespace_only_returns_no_speech(self, svc):
        with _mock_store_method("ensure_session"):
            result = await svc.process_user_message("sess_001", "   ")
        assert result["status"] == "no-speech"

    async def test_processes_message_with_all_persisted(self, svc):
        from app.models import TriageDataCore
        mock_triage = TriageDataCore(sintomas=["fiebre"], nivelPrioridad=2)

        with _mock_store_method("ensure_session"), \
             _mock_store_method("append_message"), \
             _mock_store_method("get_history", return_value=[{"role": "user", "content": "tengo fiebre"}]), \
             _mock_store_method("save_structured_data"), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.extract_preliminary_history", new_callable=AsyncMock, return_value=mock_triage), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.build_recommendation", return_value="Prioridad 2: atención pronta"):
            result = await svc.process_user_message("sess_001", "tengo fiebre")

        assert result["status"] == "success"
        assert result["transcript"] == "tengo fiebre"
        assert result["assistant_reply"] == "Prioridad 2: atención pronta"
        assert result["stage"] == "triage_completed"

    async def test_persistence_buffered_when_mongo_fails(self, svc):
        from app.models import TriageDataCore
        mock_triage = TriageDataCore(sintomas=["tos"], nivelPrioridad=3)

        with _mock_store_method("ensure_session", side_effect=Exception("DB")), \
             _mock_store_method("get_history", side_effect=Exception("DB")), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.extract_preliminary_history", new_callable=AsyncMock, return_value=mock_triage), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.build_recommendation", return_value="ok"):
            result = await svc.process_user_message("sess_002", "tengo tos")

        assert result["persistence"] == "buffered"

    async def test_empty_assistant_reply_uses_user_persistence(self, svc):
        from app.models import TriageDataCore
        mock_triage = TriageDataCore(sintomas=["tos"], nivelPrioridad=3)

        with _mock_store_method("ensure_session"), \
             _mock_store_method("append_message"), \
             _mock_store_method("get_history", return_value=[]), \
             _mock_store_method("save_structured_data", side_effect=Exception("DB")), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.extract_preliminary_history", new_callable=AsyncMock, return_value=mock_triage), \
             patch("app.services.clinical_conversation_service.triage_extraction_service.build_recommendation", return_value=""):
            result = await svc.process_user_message("sess_003", "tos seca")

        assert result["status"] == "success"


# ─── finalize_session ─────────────────────────────────────────────────────────

class TestFinalizeSession:
    async def test_empty_history_returns_empty_record(self, svc):
        with _mock_store_method("ensure_session"), \
             _mock_store_method("get_history", return_value=[]), \
             _mock_store_method("finalize_session"):
            result = await svc.finalize_session("sess_empty")
        assert result["status"] == "completed"
        assert result["final_clinical_history"]["summary"] == "No hay datos clinicos registrados."

    async def test_empty_history_buffered_when_mongo_fails(self, svc):
        with _mock_store_method("ensure_session", side_effect=Exception("DB")), \
             _mock_store_method("get_history", return_value=[]), \
             _mock_store_method("finalize_session", side_effect=Exception("DB")):
            result = await svc.finalize_session("sess_fail")
        assert result["status"] == "completed"

    async def test_finalizes_with_history(self, svc):
        history = [{"role": "user", "content": "tengo fiebre"}]
        svc._local_history["sess_full"] = history
        svc._local_structured["sess_full"] = {"symptoms": "fiebre"}

        with _mock_store_method("ensure_session"), \
             _mock_store_method("get_history", side_effect=[history, history]), \
             _mock_store_method("finalize_session"), \
             _mock_store_method("append_message"):
            result = await svc.finalize_session("sess_full")

        assert result["status"] == "completed"
        assert "fiebre" in result["final_clinical_history"]["summary"]
        assert result["final_clinical_history"]["engine"] == "deterministic-rules"

    async def test_flushes_local_messages_not_in_db(self, svc):
        history = [
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
        ]
        svc._local_history["sess_flush"] = history

        with _mock_store_method("ensure_session"), \
             _mock_store_method("get_history", side_effect=[history, history[:1]]), \
             _mock_store_method("finalize_session"), \
             _mock_store_method("append_message") as mock_append:
            await svc.finalize_session("sess_flush")

        # At least one append: extra buffered message + finalization message
        assert mock_append.call_count >= 1

    async def test_buffered_when_finalize_mongo_fails(self, svc):
        history = [{"role": "user", "content": "tos"}]
        svc._local_history["sess_err"] = history

        with _mock_store_method("ensure_session"), \
             _mock_store_method("get_history", return_value=history), \
             _mock_store_method("finalize_session", side_effect=Exception("DB")):
            result = await svc.finalize_session("sess_err")

        assert result["persistence"] == "buffered"


# ─── health ───────────────────────────────────────────────────────────────────

class TestHealth:
    async def test_returns_health_dict_healthy(self, svc):
        with patch(f"{_M}.health", new_callable=AsyncMock, return_value={"status": "healthy", "mongodb": "connected"}):
            result = await svc.health()
        assert "mongo" in result
        assert result["clinical_engine"]["status"] == "up"
        assert result["clinical_engine"]["type"] == "deterministic-rules"

    async def test_returns_health_dict_degraded(self, svc):
        with patch(f"{_M}.health", new_callable=AsyncMock, return_value={"status": "degraded", "error": "timeout"}):
            result = await svc.health()
        assert result["mongo"]["status"] == "degraded"
