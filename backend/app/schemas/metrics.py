"""Respuestas de /metrics (spec §6). Montos como string decimal, nunca float."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.invoice import InvoiceOut


class Period(BaseModel):
    date_from: date
    date_to: date


class Overview(BaseModel):
    # --- Stock: "a hoy", no dependen del período ---
    as_of: date
    client_id: uuid.UUID | None
    total_receivable: Decimal
    overdue_balance: Decimal
    # Vencido / total × 100; null si no hay saldo por cobrar (la UI muestra "N/D").
    overdue_pct: Decimal | None
    overdue_count: int
    due_soon_days: int
    due_soon_balance: Decimal
    due_soon_count: int
    credit_available: Decimal
    # --- Flujo: dependen del período ---
    period: Period
    # Cobrado = pagos vigentes (sin "saldo_a_favor") + saldo a favor recibido (ADR-0003 #18).
    collected: Decimal
    collected_payments: Decimal
    collected_credits: Decimal


class MonthlyPoint(BaseModel):
    month: str  # "AAAA-MM"
    collected: Decimal
    payments: Decimal
    credits: Decimal


class CollectionsMonthly(BaseModel):
    period: Period
    client_id: uuid.UUID | None
    total: Decimal
    items: list[MonthlyPoint]


class AgingBucket(BaseModel):
    bucket: str  # "1-30" | "31-60" | "61-90" | "91+"
    balance: Decimal
    count: int


class Aging(BaseModel):
    as_of: date
    client_id: uuid.UUID | None
    total_overdue: Decimal
    items: list[AgingBucket]


class Debtor(BaseModel):
    client_id: uuid.UUID
    client_name: str
    balance: Decimal
    overdue_balance: Decimal
    invoice_count: int


class TopDebtors(BaseModel):
    as_of: date
    items: list[Debtor]


class Upcoming(BaseModel):
    as_of: date
    days: int
    client_id: uuid.UUID | None
    total_balance: Decimal
    count: int
    items: list[InvoiceOut]
