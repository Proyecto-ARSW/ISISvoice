"""API routers package."""

from app.routers import triage_router, patient_router, health_router

__all__ = ["triage_router", "patient_router", "health_router"]
