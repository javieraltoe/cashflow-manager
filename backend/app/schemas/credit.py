import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.invoice import Amount
from app.schemas.payment import PaymentMethod, Reference


class CreditCreate(BaseModel):
    """Cobro a cuenta: dinero recibido sin factura, queda todo como saldo a favor."""

    client_id: uuid.UUID
    amount: Amount
    method: PaymentMethod
    # Si no se informa, el servicio usa la fecha de hoy (Buenos Aires).
    payment_date: date | None = None
    reference: Reference = None


class CreditApply(BaseModel):
    """Imputar saldo a favor del cliente a una de sus facturas."""

    invoice_id: uuid.UUID
    amount: Amount


class CreditOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    # "excedente": sobrante de un pago (payment_id) · "a_cuenta": cobro sin factura.
    origin: Literal["excedente", "a_cuenta"]
    payment_id: uuid.UUID | None
    credit_date: date
    amount: Decimal
    method: str
    reference: str | None
    is_void: bool
    void_reason: str | None
    voided_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    # Saldo a favor disponible del cliente después de la operación.
    client_available: Decimal


class ClientCreditBalance(BaseModel):
    client_id: uuid.UUID
    # Créditos vigentes − pagos vigentes con saldo a favor.
    credited: Decimal
    applied: Decimal
    available: Decimal
