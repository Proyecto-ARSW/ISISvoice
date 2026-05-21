"""Tests for speech_service module."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import app.services.speech_service as speech_mod


@pytest.fixture(autouse=True)
def reset_whisper_model():
    """Reset global whisper model between tests."""
    original = speech_mod._whisper_model
    speech_mod._whisper_model = None
    yield
    speech_mod._whisper_model = original


# ─── _get_model ───────────────────────────────────────────────────────────────

class TestGetModel:
    def test_loads_whisper_on_first_call(self):
        import sys
        mock_model = MagicMock()
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = speech_mod._get_model()

        mock_whisper.load_model.assert_called_once()
        assert result is mock_model
        assert speech_mod._whisper_model is mock_model

    def test_returns_cached_model_on_second_call(self):
        import sys
        mock_model = MagicMock()
        speech_mod._whisper_model = mock_model
        mock_whisper = MagicMock()

        with patch.dict(sys.modules, {"whisper": mock_whisper}):
            result = speech_mod._get_model()

        mock_whisper.load_model.assert_not_called()
        assert result is mock_model


# ─── _transcribe_via_http ─────────────────────────────────────────────────────

class TestTranscribeViaHttp:
    def _make_mock_client(self, text="hola mundo"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"text": text}
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp
        return mock_client, mock_resp

    def test_returns_transcription_text(self):
        mock_client, _ = self._make_mock_client("hola mundo")
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = speech_mod._transcribe_via_http(b"audio_bytes", "recording.mp3")
        assert result == "hola mundo"

    def test_uses_mp3_extension_from_filename(self):
        mock_client, _ = self._make_mock_client()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            speech_mod._transcribe_via_http(b"audio_bytes", "recording.mp3")
        call_str = str(mock_client.post.call_args)
        assert ".mp3" in call_str

    def test_defaults_to_wav_when_no_filename(self):
        mock_client, _ = self._make_mock_client()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            speech_mod._transcribe_via_http(b"audio_bytes", None)
        call_str = str(mock_client.post.call_args)
        assert "audio.wav" in call_str

    def test_defaults_to_wav_when_empty_extension(self):
        mock_client, _ = self._make_mock_client()
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            speech_mod._transcribe_via_http(b"audio_bytes", "noextension")
        call_str = str(mock_client.post.call_args)
        assert "audio.wav" in call_str

    def test_strips_response_text(self):
        mock_client, _ = self._make_mock_client("  texto con espacios  ")
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = speech_mod._transcribe_via_http(b"audio_bytes")
        assert result == "texto con espacios"


# ─── _decode_and_transcribe ───────────────────────────────────────────────────

class TestDecodeAndTranscribe:
    def test_uses_librosa_path(self):
        mock_audio = np.zeros(16000, dtype=np.float32)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "via librosa"}
        speech_mod._whisper_model = mock_model

        with patch("librosa.load", return_value=(mock_audio, 16000)):
            result = speech_mod._decode_and_transcribe("/fake/path.wav")

        assert result == "via librosa"
        mock_model.transcribe.assert_called_once()

    def test_transcribe_called_with_correct_params(self):
        mock_audio = np.zeros(16000, dtype=np.float32)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "prueba"}
        speech_mod._whisper_model = mock_model

        with patch("librosa.load", return_value=(mock_audio, 16000)):
            speech_mod._decode_and_transcribe("/fake/path.wav")

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs.get("fp16") is False
        assert call_kwargs.get("temperature") == 0.0

    def test_empty_text_returns_empty_string(self):
        mock_audio = np.zeros(16000, dtype=np.float32)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": ""}
        speech_mod._whisper_model = mock_model

        with patch("librosa.load", return_value=(mock_audio, 16000)):
            result = speech_mod._decode_and_transcribe("/fake/path.wav")

        assert result == ""

    def test_strips_result_text(self):
        mock_audio = np.zeros(16000, dtype=np.float32)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "  con espacios  "}
        speech_mod._whisper_model = mock_model

        with patch("librosa.load", return_value=(mock_audio, 16000)):
            result = speech_mod._decode_and_transcribe("/fake/path.wav")

        assert result == "con espacios"


# ─── transcribe_audio ─────────────────────────────────────────────────────────

class TestTranscribeAudio:
    def test_uses_http_when_api_url_set(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = "http://whisper:9000"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(b"dummy audio")
            tmp_path = tmp.name

        try:
            with patch("app.services.speech_service._transcribe_via_http", return_value="http result") as mock_http:
                result = speech_mod.transcribe_audio(tmp_path)
        finally:
            s_mod.settings.whisper_api_url = original
            os.unlink(tmp_path)

        mock_http.assert_called_once()
        assert result == "http result"

    def test_uses_local_decode_when_no_api_url(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = ""

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(b"dummy audio")
            tmp_path = tmp.name

        try:
            with patch("app.services.speech_service._decode_and_transcribe", return_value="local result") as mock_decode:
                result = speech_mod.transcribe_audio(tmp_path)
        finally:
            s_mod.settings.whisper_api_url = original
            os.unlink(tmp_path)

        mock_decode.assert_called_once_with(tmp_path)
        assert result == "local result"


# ─── transcribe_audio_bytes ───────────────────────────────────────────────────

class TestTranscribeAudioBytes:
    def test_empty_bytes_returns_empty_string(self):
        result = speech_mod.transcribe_audio_bytes(b"")
        assert result == ""

    def test_uses_http_when_api_url_set(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = "http://whisper:9000"

        with patch("app.services.speech_service._transcribe_via_http", return_value="via http") as mock_http:
            result = speech_mod.transcribe_audio_bytes(b"audio", "test.wav")

        s_mod.settings.whisper_api_url = original
        mock_http.assert_called_once_with(b"audio", "test.wav")
        assert result == "via http"

    def test_uses_local_decode_when_no_api_url(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = ""

        with patch("app.services.speech_service._decode_and_transcribe", return_value="local") as mock_decode:
            result = speech_mod.transcribe_audio_bytes(b"audio_data")

        s_mod.settings.whisper_api_url = original
        mock_decode.assert_called_once()
        assert result == "local"

    def test_custom_suffix_from_filename(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = ""

        with patch("app.services.speech_service._decode_and_transcribe", return_value="ok") as mock_decode:
            result = speech_mod.transcribe_audio_bytes(b"audio_data", "clip.ogg")

        s_mod.settings.whisper_api_url = original
        mock_decode.assert_called_once()
        tmp_path = mock_decode.call_args[0][0]
        assert tmp_path.endswith(".ogg")
        assert not os.path.exists(tmp_path)

    def test_default_suffix_wav_when_no_filename(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = ""

        with patch("app.services.speech_service._decode_and_transcribe", return_value="ok") as mock_decode:
            speech_mod.transcribe_audio_bytes(b"audio_data")

        s_mod.settings.whisper_api_url = original
        tmp_path = mock_decode.call_args[0][0]
        assert tmp_path.endswith(".wav")
        assert not os.path.exists(tmp_path)

    def test_temp_file_cleaned_up_after_decode(self):
        import app.core.settings as s_mod
        original = s_mod.settings.whisper_api_url
        s_mod.settings.whisper_api_url = ""

        captured_path = []

        def capture_and_decode(path):
            captured_path.append(path)
            return "transcribed"

        with patch("app.services.speech_service._decode_and_transcribe", side_effect=capture_and_decode):
            speech_mod.transcribe_audio_bytes(b"some_audio")

        s_mod.settings.whisper_api_url = original
        assert len(captured_path) == 1
        assert not os.path.exists(captured_path[0])
