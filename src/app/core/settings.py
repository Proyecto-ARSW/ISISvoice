import os
from pathlib import Path

from dotenv import load_dotenv


# Carga variables desde .env ubicado en la raiz del proyecto.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        self.jwt_secret = os.getenv("JWT_SECRET", "")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "medical3.1")
        self.ollama_timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "12"))
        self.ollama_max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
        self.ollama_chat_format = os.getenv("OLLAMA_CHAT_FORMAT", "")
        self.ollama_final_format = os.getenv("OLLAMA_FINAL_FORMAT", "")
        self.whisper_model = os.getenv("WHISPER_MODEL", "large-v3")
        self.whisper_language = os.getenv("WHISPER_LANGUAGE", "es")
        self.whisper_timeout_seconds = float(os.getenv("WHISPER_TIMEOUT_SECONDS", "45"))
        self.whisper_max_retries = int(os.getenv("WHISPER_MAX_RETRIES", "1"))
        self.whisper_beam_size = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
        self.whisper_best_of = int(os.getenv("WHISPER_BEST_OF", "5"))
        self.whisper_no_speech_threshold = float(os.getenv("WHISPER_NO_SPEECH_THRESHOLD", "0.45"))
        self.whisper_logprob_threshold = float(os.getenv("WHISPER_LOGPROB_THRESHOLD", "-1.0"))
        self.whisper_compression_ratio_threshold = float(os.getenv("WHISPER_COMPRESSION_RATIO_THRESHOLD", "2.2"))
        self.whisper_chunk_seconds = float(os.getenv("WHISPER_CHUNK_SECONDS", "4.0"))
        self.whisper_min_duration_seconds = float(os.getenv("WHISPER_MIN_DURATION_SECONDS", "1.2"))
        self.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongodb_db = os.getenv("MONGODB_DB", "voice_medical")
        self.mongo_server_selection_timeout_ms = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "6000"))
        self.mongo_connect_timeout_ms = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "6000"))
        self.mongo_socket_timeout_ms = int(os.getenv("MONGO_SOCKET_TIMEOUT_MS", "10000"))
        self.mongo_operation_timeout_seconds = float(os.getenv("MONGO_OPERATION_TIMEOUT_SECONDS", "2.5"))
        self.mongo_max_retries = int(os.getenv("MONGO_MAX_RETRIES", "1"))
        self.queue_max_size = int(os.getenv("SESSION_QUEUE_MAX_SIZE", "32"))
        self.max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "40"))


settings = Settings()
