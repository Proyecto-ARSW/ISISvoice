"""Standalone Whisper transcription microservice (faster-whisper backend).

Run independently:
    WHISPER_MODEL=base uvicorn whisper_app:app --host 0.0.0.0 --port 8001

Then set in main ISISvoice .env:
    WHISPER_API_URL=http://localhost:8001

Environment variables:
    WHISPER_MODEL     Model name (default: base) — tiny, base, small, medium, large-v3
    WHISPER_LANGUAGE  Language code (default: es)
"""
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "es")

app = FastAPI(title="Whisper Transcription Service", version="2.0.0")

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


@app.get("/health")
def health():
    return {"status": "ok", "model": WHISPER_MODEL, "language": WHISPER_LANGUAGE}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio file")

    suffix = Path(file.filename or "audio.wav").suffix.lower() or ".wav"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        segments, _ = _get_model().transcribe(
            tmp_path,
            language=WHISPER_LANGUAGE,
            beam_size=5,
            temperature=0.0,
            initial_prompt="Transcripcion de entrevista clinica en espanol.",
        )
        text = " ".join(s.text for s in segments).strip()
        return {"text": text, "language": WHISPER_LANGUAGE}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
