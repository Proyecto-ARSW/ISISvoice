from fastapi import APIRouter, HTTPException, Depends
from pydantic import ValidationError
from models import VitalSignsCreate
from services.triage_service import add_vital_signs
from fastapi.responses import FileResponse
from services.pdf_service import generate_triage_pdf

router = APIRouter()

@router.post("/api/nurse/vitals", responses={
    200: {"description": "Signos vitales agregados exitosamente."},
    400: {"description": "Error de validación en la entrada."},
    422: {"description": "Entidad no procesable."},
    500: {"description": "Error interno del servidor."}
})
async def add_vital_signs_endpoint(input: VitalSignsCreate):
    try:
        # Validación adicional
        if input.temperature_c is None or input.temperature_c <= 0:
            raise HTTPException(status_code=400, detail="La temperatura debe ser un valor positivo.")
        if input.heart_rate_bpm is None or input.heart_rate_bpm <= 0:
            raise HTTPException(status_code=400, detail="El ritmo cardíaco debe ser un valor positivo.")

        result = await add_vital_signs(input)
        return {"status": "success", "data": result}
    except ValidationError as ve:
        raise HTTPException(status_code=422, detail=f"Error de validación: {ve}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor.")

@router.get("/api/nurse/triages/{person_id}", responses={
    200: {"description": "Lista de triages obtenida exitosamente."},
    404: {"description": "Persona no encontrada."},
    500: {"description": "Error interno del servidor."}
})
async def list_triages(person_id: str):
    try:
        # Obtener triages asociados a la persona
        triages = await get_triages_by_person(person_id)
        if not triages:
            raise HTTPException(status_code=404, detail="No se encontraron triages para esta persona.")

        # Generar PDF con los detalles de los triages
        pdf_path = generate_triage_pdf(person_id, triages)
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"triages_{person_id}.pdf")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno del servidor.")