"""Procedure service for managing triage records and vital signs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import httpx

from app.core.settings import settings
from app.models import Comment, ProcedureRecord, TriageDataCore, VitalSignsCreate
from app.services.mongo_service import mongo_store
from app.services.triage_service import triage_extraction_service


class ProcedureService:
    """Service for managing complete procedure records."""

    def _build_webhook_payload(
        self,
        procedure: ProcedureRecord,
        webhook_delivery: str,
    ) -> dict:
        now = datetime.now(timezone.utc)
        preliminary_history = procedure.preliminary_history.model_dump()
        vital_signs = procedure.vital_signs.model_dump(exclude_none=True) if procedure.vital_signs else {
            "temperature_c": 0,
            "heart_rate_bpm": 0,
            "respiratory_rate_bpm": 0,
            "systolic_bp_mmhg": 0,
            "diastolic_bp_mmhg": 0,
            "oxygen_saturation_pct": 0,
            "weight_kg": 0,
            "height_cm": 0,
        }

        return {
            "procedure_id": procedure.procedure_id,
            "patient_id": procedure.patient_id,
            "transcript": procedure.transcript,
            "input_type": procedure.input_type,
            "preliminary_history": {
                "sintomas": preliminary_history.get("sintomas", []),
                "embarazo": preliminary_history.get("embarazo", False),
                "antecedentes": preliminary_history.get("antecedentes", []),
                "posiblesCausas": preliminary_history.get("posiblesCausas", []),
                "comentario": preliminary_history.get("comentario", ""),
                "nivelPrioridad": preliminary_history.get("nivelPrioridad", 3),
                "comentariosIA": preliminary_history.get("comentariosIA", ""),
                "advertenciaIA": preliminary_history.get(
                    "advertenciaIA",
                    triage_extraction_service.IA_WARNING,
                ),
            },
            "confidence_score": procedure.confidence_score,
            "status": procedure.status,
            "vital_signs": {
                "temperature_c": vital_signs.get("temperature_c", 0),
                "heart_rate_bpm": vital_signs.get("heart_rate_bpm", 0),
                "respiratory_rate_bpm": vital_signs.get("respiratory_rate_bpm", 0),
                "systolic_bp_mmhg": vital_signs.get("systolic_bp_mmhg", 0),
                "diastolic_bp_mmhg": vital_signs.get("diastolic_bp_mmhg", 0),
                "oxygen_saturation_pct": vital_signs.get("oxygen_saturation_pct", 0),
                "weight_kg": vital_signs.get("weight_kg", 0),
                "height_cm": vital_signs.get("height_cm", 0),
            },
            "comments": [
                {
                    "id": comment.id,
                    "comment": comment.comment,
                    "author": comment.author,
                    "created_at": comment.created_at.isoformat(),
                }
                for comment in procedure.comments
            ],
            "created_at": procedure.created_at.isoformat(),
            "updated_at": now.isoformat(),
            "webhook_delivery": webhook_delivery,
        }

    async def _deliver_webhook(self, procedure: ProcedureRecord) -> tuple[str, str]:
        if not settings.triage_webhook_url:
            return "skipped", "TRIAGE_WEBHOOK_URL no configurada"

        payload = self._build_webhook_payload(procedure, "pending")
        headers = {"Content-Type": "application/json"}
        if settings.triage_webhook_token:
            headers["x-api-key"] = settings.triage_webhook_token

        params: dict = {}
        if settings.triage_hospital_id:
            params["hospital_id"] = settings.triage_hospital_id
        if settings.triage_enfermero_id:
            params["enfermero_id"] = settings.triage_enfermero_id

        timeout = httpx.Timeout(settings.triage_webhook_timeout_seconds)
        retries = max(0, settings.triage_webhook_max_retries)
        last_error = ""

        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        settings.triage_webhook_url,
                        json=payload,
                        headers=headers,
                        params=params,
                    )
                    response.raise_for_status()
                    return "sent", f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = str(exc)
                if attempt < retries:
                    continue
        return "failed", last_error or "Unknown webhook error"

    async def create_triage_record(
        self,
        procedure_id: str,
        patient_id: str,
        transcript: str,
        input_type: str,
        triage_data_dict: dict,
        confidence_score: float,
    ) -> ProcedureRecord:
        """
        Create a new procedure record with triage data.
        
        Args:
            procedure_id: Unique procedure ID (cedula_timestamp)
            patient_cedula: Patient cedula
            transcript: Original transcript/input
            input_type: 'voice' or 'text'
            triage_data_dict: Extracted triage data
            confidence_score: Confidence of extraction
        
        Returns:
            Created procedure record
        """
        now = datetime.now(timezone.utc)

        procedure = ProcedureRecord(
            procedure_id=procedure_id,
            patient_id=patient_id,
            created_at=now,
            updated_at=now,
            transcript=transcript,
            input_type=input_type,
            preliminary_history=TriageDataCore(**triage_data_dict),
            confidence_score=confidence_score,
            status="pending",
            comments=[],
            webhook_delivery="pending",
        )

        procedure_dict = procedure.model_dump(exclude_none=True, by_alias=True)
        await mongo_store.save_procedure(procedure_dict)

        webhook_status, _ = await self._deliver_webhook(procedure)
        if webhook_status != procedure.webhook_delivery:
            await mongo_store.update_procedure(procedure_id, {"webhook_delivery": webhook_status})
            procedure.webhook_delivery = webhook_status

        return procedure

    async def get_procedure(self, procedure_id: str) -> Optional[ProcedureRecord]:
        """
        Retrieve procedure by ID.
        
        Args:
            procedure_id: Procedure ID to retrieve
        
        Returns:
            Procedure record or None
        """
        proc_doc = await mongo_store.get_procedure(procedure_id)
        if not proc_doc:
            return None
        
        return ProcedureRecord(**proc_doc)

    async def get_procedures_by_cedula(
        self,
        cedula: str,
        limit: int = 50,
    ) -> list[ProcedureRecord]:
        """
        Get all procedures for a patient by cedula.
        
        Args:
            cedula: Patient cedula
            limit: Maximum procedures to return
        
        Returns:
            List of procedures
        """
        procedures = await mongo_store.get_procedures_by_cedula(cedula, limit=limit)
        return [ProcedureRecord(**p) for p in procedures]

    async def get_patient_procedures(
        self,
        patient_id: str,
        limit: int = 50,
    ) -> list[ProcedureRecord]:
        return await self.get_procedures_by_cedula(patient_id, limit=limit)

    async def add_vital_signs(
        self,
        procedure_id: str,
        vital_signs: VitalSignsCreate,
    ) -> Optional[ProcedureRecord]:
        """
        Add or update vital signs for a procedure.
        
        Args:
            procedure_id: Procedure ID
            vital_signs: Vital signs data
        
        Returns:
            Updated procedure or None if not found
        """
        now = datetime.now(timezone.utc)
        
        update_data = {
            "vital_signs": vital_signs.model_dump(exclude_none=True),
            "vital_signs_timestamp": now,
            "updated_at": now,
            "status": "resolved",
            "webhook_delivery": "pending",
        }
        
        updated_doc = await mongo_store.update_procedure(procedure_id, update_data)
        if not updated_doc:
            return None

        procedure = ProcedureRecord(**updated_doc)
        webhook_status, _ = await self._deliver_webhook(procedure)
        final_update = {
            "webhook_delivery": webhook_status,
            "updated_at": datetime.now(timezone.utc),
        }
        final_doc = await mongo_store.update_procedure(procedure_id, final_update)
        if final_doc:
            final_doc["webhook_delivery"] = webhook_status
            return ProcedureRecord(**final_doc)

        procedure.webhook_delivery = webhook_status
        return procedure

    async def add_comment(
        self,
        procedure_id: str,
        comment_text: str,
        author: str = "system",
    ) -> Optional[ProcedureRecord]:
        """
        Add a comment to a procedure.
        
        Args:
            procedure_id: Procedure ID
            comment_text: Comment text
            author: Who is adding the comment
        
        Returns:
            Updated procedure or None if not found
        """
        now = datetime.now(timezone.utc)
        
        new_comment = Comment(
            id=str(uuid4()),
            comment=comment_text,
            created_at=now,
            author=author,
        )
        
        updated_doc = await mongo_store.add_procedure_comment(
            procedure_id,
            new_comment.model_dump(),
            now,
        )
        if not updated_doc:
            return None
        
        return ProcedureRecord(**updated_doc)

    async def list_procedures(
        self,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> list[ProcedureRecord]:
        docs = await mongo_store.list_procedures(limit=limit, status=status)
        return [ProcedureRecord(**doc) for doc in docs]

    async def get_preliminary_history(
        self,
        procedure_id: str,
    ) -> Optional[dict]:
        procedure = await self.get_procedure(procedure_id)
        if not procedure:
            return None
        return procedure.preliminary_history.model_dump()

    async def close_procedure(
        self,
        procedure_id: str,
        final_notes: Optional[str] = None,
    ) -> Optional[ProcedureRecord]:
        """
        Mark procedure as closed/completed.
        
        Args:
            procedure_id: Procedure ID
            final_notes: Optional final notes
        
        Returns:
            Updated procedure or None if not found
        """
        update_data = {
            "status": "closed",
            "updated_at": datetime.now(timezone.utc),
        }
        if final_notes:
            update_data["notes"] = final_notes
        
        updated_doc = await mongo_store.update_procedure(procedure_id, update_data)
        if not updated_doc:
            return None
        
        return ProcedureRecord(**updated_doc)


procedure_service = ProcedureService()
