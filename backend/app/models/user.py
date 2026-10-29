import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAt, UUIDPk


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class User(UUIDPk, CreatedAt, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'operator')", name="role_valid"),)

    # Se guarda siempre en minúsculas (lo normaliza el servicio).
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


class RefreshToken(UUIDPk, CreatedAt, Base):
    """Refresh tokens rotatorios. Solo se guarda el hash SHA-256, nunca el token."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Token que lo reemplazó al rotar (permite detectar reutilización).
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
