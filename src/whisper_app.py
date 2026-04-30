"""Standalone Whisper transcription microservice.

Run independently (same machine as main ISISvoice):
    WHISPER_MODEL=base uvicorn src.whisper_app:app --host 0.0.0.0 --port 8001

Then set in main ISISvoice .env:
    WHISPER_API_URL=http://localhost:8001

Environment variables:
    WHISPER_MODEL     Whisper model name (default: base)
                      Options: tiny, base, small, medium, large, large-v3
    WHISPER_LANGUAGE  Language code (default: es)
"""
import os
import tempfile
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "es")

app = FastAPI(title="Whisper Transcription Service", version="1.0.0")

_model = None


def _get_model():
    global _model
    if _model is None:
        import whisper
        _model = whisper.load_model(WHISPER_MODEL)
    return _model


@app.on_event("startup")
def load_on_startup() -> None:
    _get_model()


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

        audio: np.ndarray | None = None

        try:
            import librosa
            decoded, _ = librosa.load(tmp_path, sr=16000, mono=True)
            audio = decoded.astype(np.float32)
        except Exception:
            try:
                import torch
                import torchaudio
                waveform, sr = torchaudio.load(tmp_path)
                if waveform.ndim == 2 and waveform.shape[0] > 1:
                    waveform = waveform.mean(dim=0, keepdim=True)
                if sr != 16000:
                    waveform = torchaudio.functional.resample(waveform, sr, 16000)
                audio = waveform.squeeze(0).to(torch.float32).cpu().numpy()
            except Exception:
                import miniaudio
                import librosa as _librosa
                decoded_mini = miniaudio.decode_file(tmp_path)
                samples = np.asarray(decoded_mini.samples, dtype=np.float32)
                if decoded_mini.nchannels > 1:
                    frames = len(samples) // decoded_mini.nchannels
                    samples = samples[: frames * decoded_mini.nchannels].reshape(frames, decoded_mini.nchannels).mean(axis=1)
                samples = samples / 32768.0
                if decoded_mini.sample_rate != 16000:
                    samples = _librosa.resample(samples, orig_sr=decoded_mini.sample_rate, target_sr=16000)
                audio = samples.astype(np.float32)

        if audio is None:
            raise HTTPException(status_code=422, detail="Could not decode audio file")

        result = _get_model().transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            fp16=False,
            temperature=0.0,
            initial_prompt="Transcripcion de entrevista clinica en espanol.",
        )
        return {"text": result.get("text", "").strip(), "language": WHISPER_LANGUAGE}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription error: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
