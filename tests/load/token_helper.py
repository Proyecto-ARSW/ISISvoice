"""Generate test JWTs from local .env — never use in production."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import jwt
from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _load_secret() -> tuple[str, str]:
    env = dotenv_values(_ENV_PATH)
    secret = env.get("JWT_SECRET", "")
    algo = env.get("JWT_ALGORITHM", "HS256")
    if not secret or secret == "replace_with_main_backend_jwt_secret":
        raise RuntimeError(
            f"JWT_SECRET not set in {_ENV_PATH}. "
            "Copy .env.example → .env and fill in the real secret."
        )
    return secret, algo


def make_token(role: str, user_id: str | None = None, ttl_seconds: int = 3600) -> str:
    secret, algo = _load_secret()
    now = int(time.time())
    payload = {
        "sub": user_id or str(uuid.uuid4()),
        "rol": role,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=algo)


def paciente_token(user_id: str | None = None) -> str:
    return make_token("PACIENTE", user_id)


def enfermero_token(user_id: str | None = None) -> str:
    return make_token("ENFERMERO", user_id)


def medico_token(user_id: str | None = None) -> str:
    return make_token("MEDICO", user_id)


if __name__ == "__main__":
    print("PACIENTE:", paciente_token())
    print("ENFERMERO:", enfermero_token())
