"""Tests for MongoStore — buffer fallback, sort, health, connect logic."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mongo_service import MongoStore

_NOW = datetime.now(timezone.utc)


@pytest.fixture
def store():
    """Fresh MongoStore with no real connection."""
    return MongoStore()


@pytest.fixture
def connected_store():
    """MongoStore with a mocked connected client/db."""
    s = MongoStore()
    s._client = MagicMock()
    s._db = AsyncMock()
    return s


# ─── _safe_sort_desc ─────────────────────────────────────────────────────────

class TestSafeSortDesc:
    def test_sorts_descending(self):
        items = [
            {"id": 1, "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"id": 2, "created_at": datetime(2024, 3, 1, tzinfo=timezone.utc)},
            {"id": 3, "created_at": datetime(2024, 2, 1, tzinfo=timezone.utc)},
        ]
        result = MongoStore._safe_sort_desc(items, "created_at")
        assert [r["id"] for r in result] == [2, 3, 1]

    def test_missing_key_goes_last(self):
        # datetime.min is naive, so use naive datetimes to avoid offset-comparison error
        items = [
            {"id": 1},
            {"id": 2, "created_at": datetime(2024, 6, 1)},
        ]
        result = MongoStore._safe_sort_desc(items, "created_at")
        assert result[0]["id"] == 2

    def test_empty_list(self):
        assert MongoStore._safe_sort_desc([], "created_at") == []

    def test_single_item(self):
        items = [{"id": 1, "created_at": _NOW}]
        assert MongoStore._safe_sort_desc(items, "created_at") == items

    def test_none_value_goes_last(self):
        items = [
            {"id": 1, "created_at": None},
            {"id": 2, "created_at": datetime(2024, 1, 1)},  # naive, matches datetime.min fallback
        ]
        result = MongoStore._safe_sort_desc(items, "created_at")
        assert result[0]["id"] == 2


# ─── _now helper ─────────────────────────────────────────────────────────────

class TestNowHelper:
    def test_returns_utc_datetime(self, store):
        dt = store._now()
        assert dt.tzinfo is not None
        assert "UTC" in str(dt.tzinfo) or dt.utcoffset().total_seconds() == 0


# ─── connect ─────────────────────────────────────────────────────────────────

class TestConnect:
    async def test_already_connected_is_noop(self, store):
        store._client = MagicMock()
        with patch("app.services.mongo_service.AsyncIOMotorClient") as mock_motor:
            await store.connect()
        mock_motor.assert_not_called()

    async def test_connect_local_uri(self, store):
        mock_client = MagicMock()
        mock_db = AsyncMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_db.patients_info.create_index = AsyncMock()
        mock_db.triage_records.create_index = AsyncMock()

        import app.core.settings as s_mod
        original_uri = s_mod.settings.mongodb_uri
        s_mod.settings.mongodb_uri = "mongodb://localhost:27017"

        with patch("app.services.mongo_service.AsyncIOMotorClient", return_value=mock_client), \
             patch.object(store, "_create_indexes", new_callable=AsyncMock), \
             patch.object(store, "_flush_buffers", new_callable=AsyncMock):
            await store.connect()

        s_mod.settings.mongodb_uri = original_uri
        assert store._client is mock_client


# ─── close ───────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_disconnects(self, store):
        mock_client = MagicMock()
        store._client = mock_client
        store._db = MagicMock()
        store.close()
        mock_client.close.assert_called_once()
        assert store._client is None
        assert store._db is None

    def test_close_when_not_connected_is_noop(self, store):
        # _client is already None → should not raise
        store.close()
        assert store._client is None


# ─── save_patient ─────────────────────────────────────────────────────────────

class TestSavePatient:
    async def test_saves_to_db_when_connected(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.replace_one = AsyncMock()
        patient = {"_id": "123", "nombres": "Juan"}
        result = await connected_store.save_patient(patient)
        assert result == "123"

    async def test_buffers_when_db_raises(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.replace_one = AsyncMock(
            side_effect=Exception("DB error")
        )
        patient = {"_id": "456", "nombres": "Maria"}
        result = await connected_store.save_patient(patient)
        assert result == "456"
        assert "456" in connected_store._buffered_patients

    async def test_uses_cedula_when_no_id(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.replace_one = AsyncMock()
        patient = {"cedula": "789", "nombres": "Pedro"}
        result = await connected_store.save_patient(patient)
        assert result == "789"


# ─── get_patient ──────────────────────────────────────────────────────────────

class TestGetPatient:
    async def test_returns_from_db(self, connected_store):
        patient_doc = {"_id": "123", "nombres": "Juan"}
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one = AsyncMock(return_value=patient_doc)
        result = await connected_store.get_patient("123")
        assert result == patient_doc

    async def test_returns_none_when_not_found(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one = AsyncMock(return_value=None)
        result = await connected_store.get_patient("nonexistent")
        assert result is None

    async def test_falls_back_to_buffer_on_db_error(self, connected_store):
        connected_store._buffered_patients["456"] = {"_id": "456", "nombres": "Luis"}
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one = AsyncMock(side_effect=Exception("DB error"))
        result = await connected_store.get_patient("456")
        assert result is not None
        assert result["nombres"] == "Luis"

    async def test_returns_none_not_in_buffer_either(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one = AsyncMock(return_value=None)
        result = await connected_store.get_patient("ghost")
        assert result is None


# ─── update_patient ───────────────────────────────────────────────────────────

class TestUpdatePatient:
    async def test_updates_in_db(self, connected_store):
        updated = {"_id": "123", "nombres": "Juan Updated"}
        connected_store._db.patients_info = MagicMock()

        from pymongo import ReturnDocument
        connected_store._db.patients_info.find_one_and_update = AsyncMock(
            return_value=updated
        )
        result = await connected_store.update_patient("123", {"nombres": "Juan Updated"})
        assert result["nombres"] == "Juan Updated"

    async def test_updates_buffer_on_db_error(self, connected_store):
        connected_store._buffered_patients["789"] = {"_id": "789", "nombres": "Ana"}
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one_and_update = AsyncMock(
            side_effect=Exception("DB error")
        )
        result = await connected_store.update_patient("789", {"nombres": "Ana Updated"})
        assert result["nombres"] == "Ana Updated"

    async def test_returns_none_when_not_found(self, connected_store):
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find_one_and_update = AsyncMock(return_value=None)
        result = await connected_store.update_patient("ghost", {"nombres": "X"})
        assert result is None


# ─── save_procedure ───────────────────────────────────────────────────────────

class TestSaveProcedure:
    async def test_saves_to_db(self, connected_store):
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.insert_one = AsyncMock()
        proc = {"procedure_id": "p001", "patient_cedula": "123"}
        result = await connected_store.save_procedure(proc)
        assert result == "p001"

    async def test_buffers_on_db_error(self, connected_store):
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.insert_one = AsyncMock(
            side_effect=Exception("DB error")
        )
        proc = {"procedure_id": "p002", "patient_cedula": "456"}
        result = await connected_store.save_procedure(proc)
        assert result == "p002"
        assert "p002" in connected_store._buffered_procedures


# ─── get_procedure ────────────────────────────────────────────────────────────

class TestGetProcedure:
    async def test_returns_from_db(self, connected_store):
        proc_doc = {"procedure_id": "p001", "patient_cedula": "123"}
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find_one = AsyncMock(return_value=proc_doc)
        result = await connected_store.get_procedure("p001")
        assert result == proc_doc

    async def test_returns_none_when_not_found(self, connected_store):
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find_one = AsyncMock(return_value=None)
        result = await connected_store.get_procedure("nonexistent")
        assert result is None

    async def test_falls_back_to_buffer(self, connected_store):
        connected_store._buffered_procedures["p999"] = {
            "procedure_id": "p999", "patient_cedula": "xyz"
        }
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find_one = AsyncMock(
            side_effect=Exception("DB error")
        )
        result = await connected_store.get_procedure("p999")
        assert result is not None
        assert result["procedure_id"] == "p999"


# ─── list_patients ────────────────────────────────────────────────────────────

class TestListPatients:
    async def test_returns_db_results(self, connected_store):
        docs = [{"_id": "1"}, {"_id": "2"}]
        mock_cursor = MagicMock()
        mock_cursor.__aiter__ = MagicMock(return_value=iter(docs))
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find.return_value.sort.return_value.skip.return_value.limit.return_value = mock_cursor
        result = await connected_store.list_patients(limit=10)
        assert isinstance(result, list)

    async def test_falls_back_to_buffer_on_error(self, connected_store):
        connected_store._buffered_patients = {
            "a": {"_id": "a", "created_at": _NOW},
            "b": {"_id": "b", "created_at": _NOW},
        }
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.find.side_effect = Exception("DB error")
        result = await connected_store.list_patients()
        assert len(result) == 2


# ─── list_procedures ──────────────────────────────────────────────────────────

class TestListProcedures:
    async def test_filters_by_status_in_buffer(self, connected_store):
        connected_store._buffered_procedures = {
            "p1": {"procedure_id": "p1", "status": "pending", "updated_at": _NOW},
            "p2": {"procedure_id": "p2", "status": "resolved", "updated_at": _NOW},
        }
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find.side_effect = Exception("DB error")
        result = await connected_store.list_procedures(status="pending")
        assert all(r["status"] == "pending" for r in result)

    async def test_no_status_filter_returns_all_buffered(self, connected_store):
        connected_store._buffered_procedures = {
            "p1": {"procedure_id": "p1", "status": "pending", "updated_at": _NOW},
            "p2": {"procedure_id": "p2", "status": "resolved", "updated_at": _NOW},
        }
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find.side_effect = Exception("DB error")
        result = await connected_store.list_procedures()
        assert len(result) == 2


# ─── add_procedure_comment ────────────────────────────────────────────────────

class TestAddProcedureComment:
    async def test_returns_none_when_not_found_in_db_or_buffer(self, connected_store):
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find_one_and_update = AsyncMock(return_value=None)
        result = await connected_store.add_procedure_comment(
            "ghost_id", {"comment": "test"}, _NOW
        )
        assert result is None

    async def test_appends_comment_to_buffer(self, connected_store):
        connected_store._buffered_procedures["p_buf"] = {
            "procedure_id": "p_buf",
            "comments": [],
            "updated_at": _NOW,
        }
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.find_one_and_update = AsyncMock(
            side_effect=Exception("DB error")
        )
        result = await connected_store.add_procedure_comment(
            "p_buf", {"id": "c1", "comment": "nota"}, _NOW
        )
        assert result is not None
        assert len(result["comments"]) == 1


# ─── health ───────────────────────────────────────────────────────────────────

class TestHealth:
    async def test_healthy_when_ping_succeeds(self, connected_store):
        connected_store._db.command = AsyncMock(return_value={"ok": 1})
        result = await connected_store.health()
        assert result["status"] == "healthy"
        assert result["mongodb"] == "connected"

    async def test_degraded_when_ping_fails(self, connected_store):
        connected_store._db.command = AsyncMock(side_effect=Exception("timeout"))
        result = await connected_store.health()
        assert result["status"] == "degraded"
        assert "error" in result

    async def test_buffered_counts_in_health(self, connected_store):
        connected_store._buffered_patients["x"] = {}
        connected_store._buffered_procedures["y"] = {}
        connected_store._db.command = AsyncMock(return_value={"ok": 1})
        result = await connected_store.health()
        assert result["buffered"]["patients"] == 1
        assert result["buffered"]["procedures"] == 1


# ─── _flush_buffers ───────────────────────────────────────────────────────────

class TestFlushBuffers:
    async def test_flushes_patients_to_db(self, connected_store):
        connected_store._buffered_patients["flush_p"] = {
            "_id": "flush_p", "nombres": "Test"
        }
        connected_store._db.patients_info = MagicMock()
        connected_store._db.patients_info.replace_one = AsyncMock()
        await connected_store._flush_buffers()
        assert "flush_p" not in connected_store._buffered_patients

    async def test_flushes_procedures_to_db(self, connected_store):
        connected_store._buffered_procedures["flush_proc"] = {
            "procedure_id": "flush_proc"
        }
        connected_store._db.triage_records = MagicMock()
        connected_store._db.triage_records.replace_one = AsyncMock()
        await connected_store._flush_buffers()
        assert "flush_proc" not in connected_store._buffered_procedures

    async def test_noop_when_db_is_none(self, store):
        store._db = None
        store._buffered_patients["x"] = {}
        await store._flush_buffers()
        # DB is None → should silently skip, buffer untouched
        assert "x" in store._buffered_patients
