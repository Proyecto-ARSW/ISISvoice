"""Shared fixtures for unit tests."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest


TEST_JWT_SECRET = "test_secret_for_unit_tests_only_x"  # 32 bytes → meets HS256 minimum
TEST_JWT_ALGO = "HS256"
TEST_USER_ID = "12345678"


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    """Patch JWT secret in settings singleton for every test."""
    import app.core.settings as s_mod
    original = s_mod.settings.jwt_secret
    s_mod.settings.jwt_secret = TEST_JWT_SECRET
    yield
    s_mod.settings.jwt_secret = original


@pytest.fixture
def make_token():
    """Return a factory that builds Authorization header dicts."""
    def _make(role: str, user_id: str = TEST_USER_ID) -> dict[str, str]:
        now = int(time.time())
        payload = {"sub": user_id, "rol": role, "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGO)
        return {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
def expired_token():
    """Return an expired JWT Authorization header."""
    now = int(time.time())
    payload = {"sub": TEST_USER_ID, "rol": "PACIENTE", "iat": now - 7200, "exp": now - 3600}
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGO)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def base_client():
    """TestClient with only mongo connect + whisper model mocked (no service mocks)."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.services.mongo_service.mongo_store.connect", new_callable=AsyncMock), \
         patch("app.services.speech_service._get_model", return_value=MagicMock()):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
