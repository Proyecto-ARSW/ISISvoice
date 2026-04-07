from fastapi import APIRouter, HTTPException, Depends
from models import PatientRegistrationInput
from services.patient_service import register_patient

router = APIRouter()

@router.post("/api/patient/register")
async def register_patient_endpoint(input: PatientRegistrationInput):
    try:
        result = await register_patient(input)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))