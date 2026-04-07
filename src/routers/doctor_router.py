from fastapi import APIRouter, HTTPException, Depends
from models import CommentInput
from services.doctor_service import get_patient_history, add_comment

router = APIRouter()

@router.get("/api/doctor/history/{patientId}")
async def get_patient_history_endpoint(patientId: str):
    try:
        result = await get_patient_history(patientId)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/doctor/comment")
async def add_comment_endpoint(input: CommentInput):
    try:
        result = await add_comment(input)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))