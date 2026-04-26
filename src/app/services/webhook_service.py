from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.settings import settings
from app.models import ProcedureRecord


logger = logging.getLogger(__name__)


class WebhookService:
    """Send final triage results to an external webhook endpoint."""

    @staticmethod
    def _build_payload(procedure: ProcedureRecord) -> dict[str, Any]:
        return {
            "procedure_id": procedure.procedure_id,
            "patient_id": procedure.patient_id,
            "transcript": procedure.transcript,
            "input_type": procedure.input_type,
            "preliminary_history": procedure.triage_data.model_dump(),
            "vital_signs": procedure.vital_signs.model_dump(exclude_none=True) if procedure.vital_signs else None,
            "confidence_score": procedure.confidence_score,
            "status": procedure.status,
        }

    async def send_triage_result(self, procedure: ProcedureRecord) -> dict[str, Any]:
        if not settings.triage_api_url:
            return {"status": "skipped", "reason": "triage_api_url_not_configured"}

        headers = {
            "Content-Type": "application/json",
        }
        if settings.triage_api_key:
            headers["x-api-key"] = settings.triage_api_key

        payload = self._build_payload(procedure)

        try:
            timeout = httpx.Timeout(settings.triage_webhook_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(settings.triage_api_url, headers=headers, json=payload)
                response.raise_for_status()
            return {"status": "sent"}
        except Exception as exc:
            logger.error("Webhook delivery failed for procedure %s: %s", procedure.procedure_id, exc)
            return {"status": "failed", "reason": str(exc)}


webhook_service = WebhookService()
