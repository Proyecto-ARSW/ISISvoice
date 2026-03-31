"""Patient information service."""
from datetime import datetime
from typing import Optional, List
from app.models import PatientCreate, PatientUpdate, PatientResponse
from app.services.mongo_service import mongo_store


class PatientService:
    """Service for managing patient basic information."""

    async def create_patient(self, patient_data: PatientCreate) -> PatientResponse:
        """
        Create a new patient record.
        
        Args:
            patient_data: Patient information to create
        
        Returns:
            Created patient with timestamps
        """
        now = datetime.utcnow()
        patient_doc = patient_data.model_dump()
        patient_doc["created_at"] = now
        patient_doc["updated_at"] = now
        
        # Ensure cedula is the unique key
        patient_doc["_id"] = patient_data.cedula
        
        result = await mongo_store.save_patient(patient_doc)
        
        patient_response = PatientResponse(**patient_doc)
        return patient_response

    async def get_patient(self, cedula: str) -> Optional[PatientResponse]:
        """
        Retrieve patient by cedula.
        
        Args:
            cedula: Patient cedula/ID
        
        Returns:
            Patient data or None if not found
        """
        patient_doc = await mongo_store.get_patient(cedula)
        if not patient_doc:
            return None
        
        return PatientResponse(**patient_doc)

    async def update_patient(self, cedula: str, update_data: PatientUpdate) -> Optional[PatientResponse]:
        """
        Update patient information.
        
        Args:
            cedula: Patient cedula/ID
            update_data: Fields to update
        
        Returns:
            Updated patient or None if not found
        """
        now = datetime.utcnow()
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict["updated_at"] = now
        
        updated_doc = await mongo_store.update_patient(cedula, update_dict)
        if not updated_doc:
            return None
        
        return PatientResponse(**updated_doc)

    async def list_patients(self, limit: int = 100, skip: int = 0) -> List[PatientResponse]:
        """
        List all patients with pagination.
        
        Args:
            limit: Maximum number of results
            skip: Number of records to skip
        
        Returns:
            List of patients
        """
        patients = await mongo_store.list_patients(limit=limit, skip=skip)
        return [PatientResponse(**p) for p in patients]

    async def patient_exists(self, cedula: str) -> bool:
        """Check if patient exists."""
        patient = await mongo_store.get_patient(cedula)
        return patient is not None


patient_service = PatientService()
