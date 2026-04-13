"""Patient router removed.

This module previously exposed CRUD endpoints under `/api/v1/patient`.
The endpoints have been intentionally removed — keep this file if you
want to restore the router in the future. Currently it defines an empty
APIRouter to avoid import errors elsewhere during refactors.
"""

from fastapi import APIRouter

# Keep a minimal router object (no endpoints)
router = APIRouter(prefix="/api/v1/patient", include_in_schema=False)
