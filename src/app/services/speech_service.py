import whisper
import librosa
import numpy as np
import tempfile
import os
from pathlib import Path
import torch
import torchaudio
import miniaudio

from app.core.settings import settings


_whisper_model = None

def _get_model():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = whisper.load_model(settings.whisper_model)
    return _whisper_model


def _decode_and_transcribe(file_path: str) -> str:
    audio = None

    # Ruta principal: librosa (WAV/OGG/WEBM y muchos formatos)
    try:
        decoded, _ = librosa.load(file_path, sr=16000, mono=True)
        audio = decoded.astype(np.float32)
    except Exception:
        try:
            # Fallback 1: torchaudio (si hay soporte de codecs disponible).
            waveform, sample_rate = torchaudio.load(file_path)
            if waveform.ndim == 2 and waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            if sample_rate != 16000:
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            audio = waveform.squeeze(0).to(torch.float32).cpu().numpy()
        except Exception:
            # Fallback 2: miniaudio (sin depender de ffmpeg externo para MP3 comunes).
            decoded = miniaudio.decode_file(file_path)
            samples = np.asarray(decoded.samples, dtype=np.float32)
            if decoded.nchannels > 1:
                frame_count = len(samples) // decoded.nchannels
                samples = samples[: frame_count * decoded.nchannels].reshape(frame_count, decoded.nchannels).mean(axis=1)
            # DecodedSoundFile en SIGNED16 -> normalizacion a [-1, 1]
            samples = samples / 32768.0
            if decoded.sample_rate != 16000:
                samples = librosa.resample(samples, orig_sr=decoded.sample_rate, target_sr=16000)
            audio = samples.astype(np.float32)

    result = _get_model().transcribe(
        audio,
        language=settings.whisper_language,
        fp16=False,
        temperature=0.0,
        beam_size=settings.whisper_beam_size,
        best_of=settings.whisper_best_of,
        no_speech_threshold=settings.whisper_no_speech_threshold,
        logprob_threshold=settings.whisper_logprob_threshold,
        compression_ratio_threshold=settings.whisper_compression_ratio_threshold,
        initial_prompt="Transcripcion de entrevista clinica en espanol.",
    )
    return result.get("text", "").strip()

def transcribe_audio(file_path: str) -> str:
    return _decode_and_transcribe(file_path)


def transcribe_audio_bytes(file_bytes: bytes, original_filename: str | None = None) -> str:
    if not file_bytes:
        return ""

    suffix = ".wav"
    if original_filename:
        ext = Path(original_filename).suffix.lower().strip()
        if ext:
            suffix = ext

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        return _decode_and_transcribe(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
