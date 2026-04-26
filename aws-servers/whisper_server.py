"""
Whisper FastAPI Server for AWS EC2
Handles audio transcription via HTTP API
Listens on port 8001
"""

import base64
import logging
import tempfile
import os
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import whisper
import uvicorn
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Whisper API Server",
    version="1.0",
    description="Audio transcription via OpenAI Whisper"
)

# Global model variable
MODEL_SIZE = os.getenv("WHISPER_MODEL", "large-v3")
model = None

class TranscriptionRequest(BaseModel):
    """Request model for transcription endpoint"""
    audio_base64: str
    language: str = "es"
    file_name: str = "audio.wav"

class TranscriptionResponse(BaseModel):
    """Response model for transcription"""
    transcription: str
    language: str
    model: str
    success: bool = True

@app.on_event("startup")
async def startup_event():
    """Load Whisper model on startup"""
    global model
    try:
        logger.info(f"Loading Whisper model: {MODEL_SIZE}")
        model = whisper.load_model(MODEL_SIZE)
        logger.info(f"✓ Model {MODEL_SIZE} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load model: {str(e)}")
        raise

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "whisper-api",
        "model": MODEL_SIZE,
        "version": "1.0"
    }

@app.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(request: TranscriptionRequest):
    """
    Transcribe audio from base64-encoded audio data
    
    Args:
        audio_base64: Base64-encoded audio file
        language: ISO 639-1 language code (default: "es")
        file_name: Original filename for logging
    
    Returns:
        TranscriptionResponse with transcribed text
    """
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.audio_base64:
        raise HTTPException(status_code=400, detail="No audio data provided")
    
    temp_path = None
    try:
        # Decode base64 audio
        logger.info(f"Decoding audio: {request.file_name} ({len(request.audio_base64)} bytes base64)")
        audio_bytes = base64.b64decode(request.audio_base64)
        logger.info(f"Audio decoded: {len(audio_bytes)} bytes")
        
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Audio data is empty")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name
        
        logger.info(f"Transcribing audio ({len(audio_bytes)} bytes) with language: {request.language}")
        
        # Transcribe audio
        result = model.transcribe(
            temp_path,
            language=request.language,
            verbose=False,
            fp16=False  # Use fp32 for compatibility
        )
        
        transcription = result.get('text', '').strip()
        logger.info(f"Transcription successful: {len(transcription)} characters")
        
        return TranscriptionResponse(
            transcription=transcription,
            language=request.language,
            model=MODEL_SIZE
        )
    
    except base64.binascii.Error as e:
        logger.error(f"Invalid base64 encoding: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid base64 encoding")
    
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    
    finally:
        # Cleanup temporary file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"Cleaned up temp file: {temp_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {str(e)}")

@app.post("/transcribe-multipart", response_model=TranscriptionResponse)
async def transcribe_multipart(file: UploadFile = File(...), language: str = "es"):
    """
    Alternative endpoint that accepts multipart file upload
    
    Args:
        file: Audio file upload
        language: ISO 639-1 language code
    
    Returns:
        TranscriptionResponse with transcribed text
    """
    if not model:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    temp_path = None
    try:
        logger.info(f"Processing file: {file.filename} with language: {language}")
        
        # Read uploaded file
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(content)
            temp_path = tmp.name
        
        # Transcribe audio
        result = model.transcribe(
            temp_path,
            language=language,
            verbose=False,
            fp16=False
        )
        
        transcription = result.get('text', '').strip()
        logger.info(f"Transcription successful: {len(transcription)} characters")
        
        return TranscriptionResponse(
            transcription=transcription,
            language=language,
            model=MODEL_SIZE
        )
    
    except Exception as e:
        logger.error(f"File transcription error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {str(e)}")

@app.get("/models")
async def get_models():
    """Get available models info"""
    return {
        "current_model": MODEL_SIZE,
        "available_sizes": ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
        "description": "See https://github.com/openai/whisper for model details"
    }

@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "service": "Whisper API Server",
        "version": "1.0",
        "model": MODEL_SIZE,
        "endpoints": {
            "GET /health": "Health check",
            "GET /models": "Available models",
            "POST /transcribe": "Transcribe base64-encoded audio",
            "POST /transcribe-multipart": "Transcribe uploaded file"
        },
        "docs": "/docs",
        "openapi": "/openapi.json"
    }

if __name__ == "__main__":
    # Run server
    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting Whisper API Server on {host}:{port}")
    logger.info(f"Model: {MODEL_SIZE}")
    logger.info(f"API docs available at http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=1,  # Whisper is memory-intensive, use single worker
        log_level="info"
    )
