#!/bin/bash

# Build and push Whisper image from local machine.
# Usage:
#   IMAGE_NAME=ghcr.io/<owner>/isisvoice-whisper:cpu-latest ./aws-servers/build-and-push-whisper.sh

set -euo pipefail

if [ -z "${IMAGE_NAME:-}" ]; then
  echo "IMAGE_NAME is required"
  echo "Example: IMAGE_NAME=ghcr.io/<owner>/isisvoice-whisper:cpu-latest ./aws-servers/build-and-push-whisper.sh"
  exit 1
fi

PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
BUILDER_NAME="${BUILDER_NAME:-isisvoice-builder}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/server.py" << 'PY'
import base64
import logging
import os
import tempfile

import uvicorn
from faster_whisper import WhisperModel
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper API", version="1.0")

MODEL_SIZE = os.getenv("WHISPER_MODEL", "small")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
model = None


class TranscriptionRequest(BaseModel):
    audio_base64: str
    language: str = "es"
    file_name: str = "audio.wav"


@app.on_event("startup")
async def startup_event():
    global model
    logger.info(f"Loading Whisper model: {MODEL_SIZE} ({COMPUTE_TYPE})")
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "whisper-api",
        "model": MODEL_SIZE,
        "version": "1.0",
    }


@app.post("/transcribe")
async def transcribe(request: TranscriptionRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="No audio data")

    temp_path = None
    try:
        audio_bytes = base64.b64decode(request.audio_base64)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        segments, _ = model.transcribe(temp_path, language=request.language)
        text = "".join(segment.text for segment in segments).strip()

        return {
            "transcription": text,
            "language": request.language,
            "model": MODEL_SIZE,
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
PY

cat > "$TMP_DIR/Dockerfile" << 'DOCKER'
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    faster-whisper \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    pydantic

COPY server.py /app/server.py

EXPOSE 8001
CMD ["python", "/app/server.py"]
DOCKER

if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER_NAME" --use
else
  docker buildx use "$BUILDER_NAME"
fi

docker buildx build \
  --platform "$PLATFORMS" \
  -t "$IMAGE_NAME" \
  --push \
  "$TMP_DIR"

echo "Image pushed: $IMAGE_NAME"
