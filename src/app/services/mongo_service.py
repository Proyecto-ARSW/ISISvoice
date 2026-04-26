"""MongoDB service for clinical triage data persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, List

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from app.core.settings import settings


class MongoStore:
    """MongoDB store for medical triage records and patient information."""

    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db = None
        self._buffered_patients: dict[str, dict[str, Any]] = {}
        self._buffered_procedures: dict[str, dict[str, Any]] = {}

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    async def connect(self) -> None:
        """Connect to MongoDB with retry logic."""
        if self._client is not None:
            return
        
        common_options = {
            "serverSelectionTimeoutMS": settings.mongo_server_selection_timeout_ms,
            "connectTimeoutMS": settings.mongo_connect_timeout_ms,
            "socketTimeoutMS": settings.mongo_socket_timeout_ms,
            "retryWrites": True,
        }
        
        if settings.mongodb_uri.startswith("mongodb+srv://"):
            self._client = AsyncIOMotorClient(
                settings.mongodb_uri,
                tls=True,
                tlsCAFile=certifi.where(),
                **common_options,
            )
        else:
            self._client = AsyncIOMotorClient(settings.mongodb_uri, **common_options)
        
        self._db = self._client[settings.mongodb_db]
        await self._create_indexes()
        await self._flush_buffers()

    async def _flush_buffers(self) -> None:
        """Flush buffered data to MongoDB after reconnection."""
        if self._db is None:
            return

        if self._buffered_patients:
            patients = self._db.patients_info
            for cedula, patient_doc in list(self._buffered_patients.items()):
                await patients.replace_one({"_id": cedula}, patient_doc, upsert=True)
                self._buffered_patients.pop(cedula, None)

        if self._buffered_procedures:
            procedures = self._db.triage_records
            for procedure_id, procedure_doc in list(self._buffered_procedures.items()):
                await procedures.replace_one(
                    {"procedure_id": procedure_id},
                    procedure_doc,
                    upsert=True,
                )
                self._buffered_procedures.pop(procedure_id, None)

    @staticmethod
    def _safe_sort_desc(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        return sorted(items, key=lambda x: x.get(key) or datetime.min, reverse=True)

    async def _create_indexes(self) -> None:
        """Create necessary indexes for optimal query performance."""
        try:
            # Patient info collection indexes
            patients_col = self._db.patients_info
            await patients_col.create_index("cedula", unique=True)
            await patients_col.create_index("created_at")
            
            # Procedure records collection indexes
            procedures_col = self._db.triage_records
            await procedures_col.create_index("procedure_id", unique=True)
            await procedures_col.create_index("patient_id")
            await procedures_col.create_index("patient_cedula")
            await procedures_col.create_index("created_at")
            await procedures_col.create_index([("patient_id", 1), ("created_at", -1)])
            await procedures_col.create_index([("patient_cedula", 1), ("created_at", -1)])
            
        except Exception as e:
            # Indexes might already exist, that's fine
            pass

    async def close(self) -> None:
        """Close MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

    # ========== Patient Mana gement Methods ==========

    async def save_patient(self, patient_doc: dict[str, Any]) -> str:
        """
        Save or update patient information.
        
        Args:
            patient_doc: Patient document with _id as cedula
        
        Returns:
            Cedula (patient ID)
        """
        cedula = patient_doc.get("_id") or patient_doc.get("cedula")
        patient_doc["_id"] = cedula

        try:
            await self.connect()
            patients = self._db.patients_info
            await patients.replace_one({"_id": cedula}, patient_doc, upsert=True)
        except Exception:
            self._buffered_patients[cedula] = patient_doc
        return cedula

    async def get_patient(self, cedula: str) -> Optional[dict[str, Any]]:
        """
        Retrieve patient by cedula.
        
        Args:
            cedula: Patient cedula
        
        Returns:
            Patient document or None
        """
        try:
            await self.connect()
            patients = self._db.patients_info
            doc = await patients.find_one({"_id": cedula})
            if doc is not None:
                return doc
        except Exception:
            pass
        return self._buffered_patients.get(cedula)

    async def update_patient(
        self,
        cedula: str,
        update_dict: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """
        Update patient information.
        
        Args:
            cedula: Patient cedula
            update_dict: Fields to update
        
        Returns:
            Updated patient document or None if not found
        """
        try:
            await self.connect()
            patients = self._db.patients_info
            result = await patients.find_one_and_update(
                {"_id": cedula},
                {"$set": update_dict},
                return_document=ReturnDocument.AFTER,
            )
            if result is not None:
                return result
        except Exception:
            pass

        buffered = self._buffered_patients.get(cedula)
        if buffered is None:
            return None
        buffered.update(update_dict)
        self._buffered_patients[cedula] = buffered
        return buffered

    async def list_patients(
        self,
        limit: int = 100,
        skip: int = 0
    ) -> List[dict[str, Any]]:
        """
        List all patients with pagination.
        
        Args:
            limit: Maximum results
            skip: Records to skip
        
        Returns:
            List of patient documents
        """
        docs: list[dict[str, Any]] = []
        try:
            await self.connect()
            patients = self._db.patients_info
            cursor = patients.find().sort("created_at", -1).skip(skip).limit(limit)
            async for doc in cursor:
                docs.append(doc)
        except Exception:
            docs = []

        if not docs and self._buffered_patients:
            docs = self._safe_sort_desc(list(self._buffered_patients.values()), "created_at")
            docs = docs[skip : skip + limit]

        return docs

    # ========== Procedure/Triage Management Methods ==========

    async def save_procedure(self, procedure_doc: dict[str, Any]) -> str:
        """
        Save a new procedure record.
        
        Args:
            procedure_doc: Procedure document
        
        Returns:
            Procedure ID
        """
        try:
            await self.connect()
            procedures = self._db.triage_records
            await procedures.insert_one(procedure_doc)
        except Exception:
            self._buffered_procedures[procedure_doc["procedure_id"]] = procedure_doc
        return procedure_doc["procedure_id"]

    async def get_procedure(self, procedure_id: str) -> Optional[dict[str, Any]]:
        """
        Retrieve procedure by ID.
        
        Args:
            procedure_id: Procedure ID
        
        Returns:
            Procedure document or None
        """
        try:
            await self.connect()
            procedures = self._db.triage_records
            doc = await procedures.find_one({"procedure_id": procedure_id})
            if doc is not None:
                return doc
        except Exception:
            pass
        return self._buffered_procedures.get(procedure_id)

    async def get_procedures_by_patient_id(
        self,
        patient_id: str,
        limit: int = 50
    ) -> List[dict[str, Any]]:
        """
        Get all procedures for a patient.
        
        Args:
            patient_id: Patient identifier from JWT
            limit: Maximum results
        
        Returns:
            List of procedure documents
        """
        docs: list[dict[str, Any]] = []
        try:
            await self.connect()
            procedures = self._db.triage_records
            cursor = (
                procedures.find({"$or": [{"patient_id": patient_id}, {"patient_cedula": patient_id}]})
                .sort("created_at", -1)
                .limit(limit)
            )
            async for doc in cursor:
                docs.append(doc)
        except Exception:
            docs = []

        if not docs and self._buffered_procedures:
            buffered = [
                p
                for p in self._buffered_procedures.values()
                if p.get("patient_id") == patient_id or p.get("patient_cedula") == patient_id
            ]
            docs = self._safe_sort_desc(buffered, "created_at")[:limit]

        return docs

    async def get_procedures_by_cedula(self, cedula: str, limit: int = 50) -> List[dict[str, Any]]:
        """Backward compatible wrapper; use get_procedures_by_patient_id."""
        return await self.get_procedures_by_patient_id(cedula, limit=limit)

    async def update_procedure(
        self,
        procedure_id: str,
        update_dict: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """
        Update procedure record.
        
        Args:
            procedure_id: Procedure ID
            update_dict: Fields to update
        
        Returns:
            Updated procedure or None if not found
        """
        try:
            await self.connect()
            procedures = self._db.triage_records
            result = await procedures.find_one_and_update(
                {"procedure_id": procedure_id},
                {"$set": update_dict},
                return_document=ReturnDocument.AFTER,
            )
            if result is not None:
                return result
        except Exception:
            pass

        buffered = self._buffered_procedures.get(procedure_id)
        if buffered is None:
            return None
        buffered.update(update_dict)
        self._buffered_procedures[procedure_id] = buffered
        return buffered

    async def add_procedure_comment(
        self,
        procedure_id: str,
        comment_doc: dict[str, Any],
        timestamp: datetime
    ) -> Optional[dict[str, Any]]:
        """
        Add a comment to a procedure.
        
        Args:
            procedure_id: Procedure ID
            comment_doc: Comment document
            timestamp: Update timestamp
        
        Returns:
            Updated procedure or None
        """
        try:
            await self.connect()
            procedures = self._db.triage_records
            result = await procedures.find_one_and_update(
                {"procedure_id": procedure_id},
                {
                    "$push": {"comments": comment_doc},
                    "$set": {"updated_at": timestamp},
                },
                return_document=ReturnDocument.AFTER,
            )
            if result is not None:
                return result
        except Exception:
            pass

        buffered = self._buffered_procedures.get(procedure_id)
        if buffered is None:
            return None
        comments = list(buffered.get("comments") or [])
        comments.append(comment_doc)
        buffered["comments"] = comments
        buffered["updated_at"] = timestamp
        self._buffered_procedures[procedure_id] = buffered
        return buffered

    # ========== Health Check ==========

    async def health(self) -> dict[str, Any]:
        """Check MongoDB connection health."""
        try:
            await self.connect()
            await self._db.command("ping")
            return {
                "status": "healthy",
                "mongodb": "connected",
                "buffered": {
                    "patients": len(self._buffered_patients),
                    "procedures": len(self._buffered_procedures),
                },
            }
        except Exception as exc:
            return {
                "status": "degraded",
                "mongodb": "disconnected",
                "error": str(exc),
                "buffered": {
                    "patients": len(self._buffered_patients),
                    "procedures": len(self._buffered_procedures),
                },
            }


# Singleton instance
mongo_store = MongoStore()
