"""
Speech service for transcribing audio using remote Whisper API on AWS.
Instead of loading Whisper locally, this service calls the remote API endpoint.
"""
import base64
import tempfile
import os
from pathlib import Path
import httpx
import logging

from app.core.settings import settings

logger = logging.getLogger(__name__)


async def _transcribe_remote(file_bytes: bytes, original_filename: str | None = None) -> str:
    """
    Send audio to remote Whisper API on AWS and return transcription.
    
    Args:
        file_bytes: Raw audio file bytes
        original_filename: Original filename (for extension hint)
    
    Returns:
        Transcribed text, or error message if failed
    """
    if not file_bytes:
        return ""
    
    try:
        # Encode audio as base64 for transmission
        audio_base64 = base64.b64encode(file_bytes).decode('utf-8')
        
        payload = {
            "audio_base64": audio_base64,
            "language": settings.whisper_language,
            "file_name": original_filename or "audio.wav"
        }
        
        timeout = httpx.Timeout(settings.whisper_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.whisper_api_url}/transcribe",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            transcription = data.get("transcription", "").strip()
            
            if not transcription:
                logger.warning("Whisper API returned empty transcription")
                return "[Error: Whisper returned empty transcription]"
            
            return transcription
    
    except httpx.TimeoutException:
        logger.error(f"Whisper API timeout after {settings.whisper_timeout_seconds}s")
        return "[Error: Whisper API timeout]"
    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to Whisper API at {settings.whisper_api_url}: {str(e)}")
        return f"[Error: Cannot reach Whisper API at {settings.whisper_api_url}]"
    except Exception as e:
        logger.error(f"Whisper API error: {str(e)}")
        return f"[Error: Whisper API error - {str(e)}]"


def transcribe_audio_bytes(file_bytes: bytes, original_filename: str | None = None) -> str:
    """
    Synchronous wrapper for async transcription.
    Calls remote Whisper API on AWS.
    
    Args:
        file_bytes: Raw audio file bytes
        original_filename: Optional filename
    
    Returns:
        Transcribed text
    """
    import asyncio
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_transcribe_remote(file_bytes, original_filename))
