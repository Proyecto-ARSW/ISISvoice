"""Tests for main FastAPI app (lifespan, middleware, base routes)."""
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


# ─── base routes ──────────────────────────────────────────────────────────────

class TestBaseRoutes:
    def test_root_redirects_to_docs(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (301, 302, 307, 308)
        assert "/docs" in r.headers.get("location", "")

    def test_client_html_exists_returns_file(self, client):
        with patch("app.main._CLIENT_HTML") as mock_path:
            mock_path.exists.return_value = True
            mock_path.__str__ = lambda s: "client.html"
            with patch("app.main.FileResponse") as mock_fr:
                mock_fr.return_value = MagicMock(status_code=200)
                r = client.get("/client.html")
        assert r.status_code in (200, 307, 308)

    def test_client_html_not_exists_redirects(self, client):
        with patch("app.main._CLIENT_HTML") as mock_path:
            mock_path.exists.return_value = False
            r = client.get("/client.html", follow_redirects=False)
        assert r.status_code in (301, 302, 307, 308)
