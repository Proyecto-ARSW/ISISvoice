"""Health check endpoints."""
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings import settings
from app.services.mongo_service import mongo_store


router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str
    version: str
    dependencies: dict


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint",
    description="Check service and dependency health status."
)
async def health_check() -> HealthResponse:
    """
    Check service and dependencies health.
    
    Returns:
        Health status with dependency information
    """
    dependencies = {}
    overall_status = "healthy"
    
    # Check MongoDB
    mongo_health = await mongo_store.health()
    dependencies["mongodb"] = mongo_health
    if mongo_health.get("status") != "healthy":
        overall_status = "degraded"
    
    # Check remote Whisper service
    try:
        timeout = httpx.Timeout(4.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{settings.whisper_api_url}/health")
            response.raise_for_status()
        dependencies["whisper"] = {"status": "reachable", "url": settings.whisper_api_url}
    except Exception as e:
        dependencies["whisper"] = {
            "status": "unreachable",
            "url": settings.whisper_api_url,
            "error": str(e),
        }
        overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        service="Voice Medical Triage Service",
        version="1.0.0",
        dependencies=dependencies,
    )


@router.get(
    "/ready",
    response_model=dict,
    summary="Readiness probe",
    description="Check if service is ready to receive requests."
)
async def readiness() -> dict:
    """Kubernetes/container readiness probe."""
    mongo_health = await mongo_store.health()
    is_ready = mongo_health.get("status") == "healthy"
    return {
        "ready": is_ready,
        "mongodb": mongo_health.get("status"),
    }


@router.get(
    "/live",
    response_model=dict,
    summary="Liveness probe",
    description="Check if service is alive."
)
async def liveness() -> dict:
    """Kubernetes/container liveness probe."""
    return {"alive": True, "service": "Voice Medical Triage Service"}
