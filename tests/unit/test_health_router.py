"""Tests for health check endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


HEALTHY_MONGO = {
    "status": "healthy",
    "mongodb": "connected",
    "buffered": {"patients": 0, "procedures": 0},
}

DEGRADED_MONGO = {
    "status": "degraded",
    "mongodb": "disconnected",
    "error": "connection timeout",
}


@pytest.fixture
def healthy_client():
    from app.main import app
    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.routers.health_router.mongo_store.health", new_callable=AsyncMock,
               return_value=HEALTHY_MONGO), \
         patch("app.routers.health_router._get_model", return_value=MagicMock()):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture
def degraded_client():
    from app.main import app
    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.routers.health_router.mongo_store.health", new_callable=AsyncMock,
               return_value=DEGRADED_MONGO), \
         patch("app.routers.health_router._get_model", return_value=MagicMock()):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


@pytest.fixture
def whisper_error_client():
    from app.main import app
    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.routers.health_router.mongo_store.health", new_callable=AsyncMock,
               return_value=HEALTHY_MONGO), \
         patch("app.routers.health_router._get_model", side_effect=RuntimeError("model not found")):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ─── GET /api/v1/health ───────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, healthy_client):
        r = healthy_client.get("/api/v1/health")
        assert r.status_code == 200

    def test_response_has_required_fields(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert "dependencies" in data

    def test_healthy_when_mongo_connected(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert data["status"] == "healthy"

    def test_degraded_when_mongo_down(self, degraded_client):
        data = degraded_client.get("/api/v1/health").json()
        assert data["status"] == "degraded"

    def test_mongodb_dependency_present(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert "mongodb" in data["dependencies"]

    def test_whisper_dependency_present(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert "whisper" in data["dependencies"]

    def test_whisper_loaded_status(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert data["dependencies"]["whisper"]["status"] == "loaded"

    def test_whisper_error_degrades_service(self, whisper_error_client):
        data = whisper_error_client.get("/api/v1/health").json()
        assert data["status"] == "degraded"
        assert data["dependencies"]["whisper"]["status"] == "error"

    def test_service_name_in_response(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert "Voice" in data["service"] or "Triage" in data["service"]

    def test_version_in_response(self, healthy_client):
        data = healthy_client.get("/api/v1/health").json()
        assert data["version"] == "1.0.0"


# ─── GET /api/v1/ready ────────────────────────────────────────────────────────

class TestReadinessEndpoint:
    def test_returns_200(self, healthy_client):
        r = healthy_client.get("/api/v1/ready")
        assert r.status_code == 200

    def test_ready_true_when_healthy(self, healthy_client):
        data = healthy_client.get("/api/v1/ready").json()
        assert data["ready"] is True

    def test_ready_false_when_degraded(self, degraded_client):
        data = degraded_client.get("/api/v1/ready").json()
        assert data["ready"] is False

    def test_mongodb_field_in_response(self, healthy_client):
        data = healthy_client.get("/api/v1/ready").json()
        assert "mongodb" in data

    def test_mongodb_connected_when_healthy(self, healthy_client):
        data = healthy_client.get("/api/v1/ready").json()
        assert data["mongodb"] == "healthy"


# ─── GET /api/v1/live ─────────────────────────────────────────────────────────

class TestLivenessEndpoint:
    def test_returns_200(self, healthy_client):
        r = healthy_client.get("/api/v1/live")
        assert r.status_code == 200

    def test_alive_is_true(self, healthy_client):
        data = healthy_client.get("/api/v1/live").json()
        assert data["alive"] is True

    def test_service_field_present(self, healthy_client):
        data = healthy_client.get("/api/v1/live").json()
        assert "service" in data

    def test_live_even_when_mongo_degraded(self, degraded_client):
        r = degraded_client.get("/api/v1/live")
        assert r.status_code == 200
        assert r.json()["alive"] is True


# ─── Root redirect ────────────────────────────────────────────────────────────

class TestRootRedirect:
    def test_root_redirects(self, healthy_client):
        r = healthy_client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)
