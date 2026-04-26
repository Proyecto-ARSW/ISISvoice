"""Procedure service for managing triage records and vital signs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.models import Comment, ProcedureRecord, TriageDataCore, VitalSignsCreate
from app.services.mongo_service import mongo_store
from app.services.webhook_service import webhook_service


class ProcedureService:
    """Service for managing complete procedure records."""

    @staticmethod
    def _normalize_procedure_doc(doc: dict) -> dict:
        normalized = dict(doc)
        if "patient_id" not in normalized and "patient_cedula" in normalized:
            normalized["patient_id"] = normalized.pop("patient_cedula")

        triage_payload = normalized.get("triage_data") or normalized.get("preliminary_history") or {}
        if isinstance(triage_payload, dict):
            triage_payload.pop("idpaciente", None)
            normalized["triage_data"] = triage_payload

        return normalized

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
            procedure_id: Unique procedure ID
            patient_id: Patient identifier from JWT
            transcript: Original transcript/input
            input_type: 'voice' or 'text'
            triage_data_dict: Extracted triage data
            confidence_score: Confidence of extraction
        
        Returns:
            Created procedure record
        """
        now = datetime.now(timezone.utc)
        clean_triage_data = dict(triage_data_dict)
        clean_triage_data.pop("idpaciente", None)

        procedure = ProcedureRecord(
            procedure_id=procedure_id,
            patient_id=patient_id,
            created_at=now,
            updated_at=now,
            transcript=transcript,
            input_type=input_type,
            triage_data=TriageDataCore(**clean_triage_data),
            confidence_score=confidence_score,
            status="triage_completed",
            comments=[],
        )

        # Save to MongoDB
        procedure_dict = procedure.model_dump(exclude_none=True)
        await mongo_store.save_procedure(procedure_dict)

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

        return ProcedureRecord(**self._normalize_procedure_doc(proc_doc))

    async def get_procedures_by_patient_id(
        self,
        patient_id: str,
        limit: int = 50,
    ) -> list[ProcedureRecord]:
        """
        Get all procedures for a patient by identifier from JWT.
        
        Args:
            patient_id: Patient identifier
            limit: Maximum procedures to return
        
        Returns:
            List of procedures
        """
        procedures = await mongo_store.get_procedures_by_patient_id(patient_id, limit=limit)
        return [ProcedureRecord(**self._normalize_procedure_doc(p)) for p in procedures]

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
            "status": "vital_signs_recorded",
        }
        
        updated_doc = await mongo_store.update_procedure(procedure_id, update_data)
        if not updated_doc:
            return None

        return ProcedureRecord(**self._normalize_procedure_doc(updated_doc))

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

        return ProcedureRecord(**self._normalize_procedure_doc(updated_doc))

    async def get_preliminary_history(
        self,
        procedure_id: str,
    ) -> Optional[dict]:
        procedure = await self.get_procedure(procedure_id)
        if not procedure:
            return None
        return procedure.triage_data.model_dump()

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

        return ProcedureRecord(**self._normalize_procedure_doc(updated_doc))

    async def send_to_webhook(self, procedure_id: str) -> str:
        """Send sanitized triage payload to external webhook as final step."""
        procedure = await self.get_procedure(procedure_id)
        if not procedure:
            return "not_found"

        webhook_result = await webhook_service.send_triage_result(procedure)
        return webhook_result.get("status", "error")


procedure_service = ProcedureService()
