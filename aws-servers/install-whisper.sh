#!/bin/bash

# Whisper Server Installation Script for AWS EC2
# Run this on Ubuntu 22.04 LTS EC2 instance
# Usage: chmod +x install-whisper.sh && ./install-whisper.sh

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║       Whisper Server Installation for AWS EC2                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Update system
echo "[1/6] Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing dependencies..."
sudo apt install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    wget \
    curl \
    ffmpeg

# Create virtual environment
echo "[3/6] Creating Python virtual environment..."
sudo mkdir -p /opt/whisper
sudo python3.11 -m venv /opt/whisper-env
source /opt/whisper-env/bin/activate

# Install Python packages
echo "[4/6] Installing Python packages..."
pip install --upgrade pip setuptools wheel
pip install \
    openai-whisper \
    fastapi \
    uvicorn[standard] \
    python-multipart \
    pydantic \
    torch \
    torchaudio

# Download whisper server script
echo "[5/6] Setting up Whisper server script..."
sudo tee /opt/whisper_server.py > /dev/null << 'WHISPER_EOF'
"""
Whisper FastAPI Server for AWS EC2
Handles audio transcription via HTTP API
"""

import base64
import logging
import tempfile
import os
from fastapi import FastAPI, HTTPException, File, UploadFile
from pydantic import BaseModel
import whisper
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Whisper API Server", version="1.0")

MODEL_SIZE = os.getenv("WHISPER_MODEL", "large-v3")
model = None

class TranscriptionRequest(BaseModel):
    audio_base64: str
    language: str = "es"
    file_name: str = "audio.wav"

@app.on_event("startup")
async def startup_event():
    global model
    logger.info(f"Loading Whisper model: {MODEL_SIZE}")
    model = whisper.load_model(MODEL_SIZE)
    logger.info(f"Model {MODEL_SIZE} loaded successfully")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "whisper-api",
        "model": MODEL_SIZE,
        "version": "1.0"
    }

@app.post("/transcribe")
async def transcribe(request: TranscriptionRequest):
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="No audio data provided")
    
    temp_path = None
    try:
        audio_bytes = base64.b64decode(request.audio_base64)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name
        
        result = model.transcribe(
            temp_path,
            language=request.language,
            verbose=False,
            fp16=False
        )
        
        return {
            "transcription": result.get('text', '').strip(),
            "language": request.language,
            "model": MODEL_SIZE
        }
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, workers=1)
WHISPER_EOF

# Create systemd service
echo "[6/6] Creating systemd service..."
sudo tee /etc/systemd/system/whisper.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=Whisper API Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt
Environment="PATH=/opt/whisper-env/bin"
Environment="WHISPER_MODEL=large-v3"
Environment="PORT=8001"
ExecStart=/opt/whisper-env/bin/python /opt/whisper_server.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable whisper
sudo systemctl start whisper

# Wait for service to start
sleep 3

# Check status
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                   INSTALLATION COMPLETE                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Service Status:"
sudo systemctl status whisper

echo ""
echo "Testing health endpoint:"
curl http://localhost:8001/health || echo "Service not yet ready, waiting..."

echo ""
echo "✓ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Wait 2-3 minutes for model to load (check logs)"
echo "2. Monitor progress: journalctl -u whisper -f"
echo "3. Test endpoint: curl http://INSTANCE_IP:8001/health"
echo ""
