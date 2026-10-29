"""Registro de auditoría: quién hizo qué, sobre qué entidad y cuándo (UTC)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent

# Campos que nunca deben quedar en la auditoría.
_SENSITIVE = {"password", "password_hash", "token", "refresh_token", "token_hash"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items() if k not in _SENSITIVE}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


def record(
    db: Session,
    *,
    actor_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Agrega el evento a la sesión; se confirma junto con la operación (misma transacción)."""
    db.add(
        AuditEvent(
            actor_user_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=_jsonable(details or {}),
        )
    )


def diff(obj: Any, changes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{campo: {"from": antes, "to": después}} solo para los campos que cambian."""
    out: dict[str, dict[str, Any]] = {}
    for field, new in changes.items():
        old = getattr(obj, field)
        if old != new:
            out[field] = {"from": old, "to": new}
    return out
