import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAt, UpdatedAt, UUIDPk

MONEY = Numeric(15, 2)


class Invoice(UUIDPk, CreatedAt, UpdatedAt, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("client_id", "invoice_number", name="uq_invoices_client_number"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("currency = 'ARS'", name="currency_ars"),
        CheckConstraint("due_date >= issue_date", name="due_after_issue"),
        Index("ix_invoices_client_id_due_date", "client_id", "due_date"),
        Index("ix_invoices_due_date_active", "due_date", postgresql_where=text("NOT is_void")),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="ARS")
    description: Mapped[str | None] = mapped_column(Text)
    is_void: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
