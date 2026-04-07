"""Procedure service for managing triage records and vital signs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.models import Comment, ProcedureRecord, TriageDataCore, VitalSignsCreate
from app.services.mongo_service import mongo_store


class ProcedureService:
    """Service for managing complete procedure records."""

    async def create_triage_record(
        self,
        procedure_id: str,
        patient_cedula: str,
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
            patient_cedula=patient_cedula,
            created_at=now,
            updated_at=now,
            transcript=transcript,
            input_type=input_type,
            triage_data=TriageDataCore(**triage_data_dict),
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
        
        return ProcedureRecord(**updated_doc)

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
        
        return ProcedureRecord(**updated_doc)


procedure_service = ProcedureService()
