import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Mock JWT tokens
VALID_JWT = "Bearer valid.jwt.token"
INVALID_JWT = "Bearer invalid.jwt.token"

# Test protected route with valid JWT
def test_protected_route_with_valid_jwt():
    response = client.get(
        "/api/v1/health/protected",
        headers={"Authorization": VALID_JWT},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Access granted"}

# Test protected route with invalid JWT
def test_protected_route_with_invalid_jwt():
    response = client.get(
        "/api/v1/health/protected",
        headers={"Authorization": INVALID_JWT},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token JWT invalido"

# Test protected route without JWT
def test_protected_route_without_jwt():
    response = client.get("/api/v1/health/protected")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"