from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import settings


security = HTTPBearer(auto_error=True)


class AuthUser:
    def __init__(self, user_id: str, role: str) -> None:
        self.user_id = user_id
        self.role = role


class JwtRole:
    PACIENTE = "PACIENTE"
    ENFERMERO = "ENFERMERO"
    MEDICO = "MEDICO"
    ADMIN = "ADMIN"
    RECEPCIONISTA = "RECEPCIONISTA"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT expirado",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT invalido",
        ) from exc

    user_id = str(payload.get("sub") or "").strip()
    role = str(payload.get("rol") or "").strip().upper()

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT sin claims requeridos",
        )

    return AuthUser(user_id=user_id, role=role)


def require_roles(*allowed_roles: str) -> Callable[[AuthUser], AuthUser]:
    allowed = {role.upper() for role in allowed_roles}

    async def _role_dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta operacion",
            )
        return user

    return _role_dependency
