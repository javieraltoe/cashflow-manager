"""Saldo a favor del cliente (ADR-0003 #6).

Cada fila es dinero recibido que todavía no se imputó a una factura: el excedente de un
pago (payment_id apunta al pago que lo originó) o un cobro a cuenta sin factura
(payment_id NULL). Se consume registrando pagos con método "saldo_a_favor".
Crédito disponible = créditos vigentes − pagos vigentes "saldo_a_favor" del cliente.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.invoice import MONEY
from app.models.mixins import CreatedAt, UUIDPk


class ClientCredit(UUIDPk, CreatedAt, Base):
    __tablename__ = "client_credits"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index(
            "ix_client_credits_client_id_active", "client_id", postgresql_where=text("NOT is_void")
        ),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    # Pago que generó el excedente; NULL = cobro a cuenta.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("payments.id", ondelete="RESTRICT"), unique=True
    )
    credit_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    is_void: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    void_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
