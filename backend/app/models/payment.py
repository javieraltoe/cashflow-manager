"""Pagos. La tabla se crea en el Sprint 1 (el saldo depende de ella); el servicio de
registro/anulación con bloqueo FOR UPDATE se implementa en el Sprint 2."""

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


class Payment(UUIDPk, CreatedAt, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_invoice_id_active", "invoice_id", postgresql_where=text("NOT is_void")),
        Index("ix_payments_payment_date", "payment_date"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    is_void: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    void_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
