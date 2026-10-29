"""Dependencias comunes: sesión de DB, usuario autenticado y control de rol."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.core.timeutils import today_local
from app.db.session import get_db
from app.models import Role, User

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(message: str = "Autenticación requerida") -> AppError:
    return AppError(
        "unauthorized",
        message,
        status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _unauthorized("Token inválido o vencido")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise _unauthorized("Token inválido o vencido") from exc
    # Rol y estado se leen SIEMPRE de la base: desactivar un usuario es inmediato.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Usuario inexistente o inactivo")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise AppError(
            "forbidden",
            "Solo un administrador puede realizar esta acción",
            status.HTTP_403_FORBIDDEN,
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_today() -> date:
    """Fecha de negocio de hoy (America/Argentina/Buenos_Aires). Se puede sobreescribir en tests."""
    return today_local()


Today = Annotated[date, Depends(get_today)]
