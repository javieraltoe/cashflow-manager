import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, StringConstraints

from app.schemas.common import clean_optional
from app.schemas.invoice import Amount
from app.services.invoice_rules import InvoiceStatus


class PaymentMethod(StrEnum):
    EFECTIVO = "efectivo"
    TRANSFERENCIA = "transferencia"
    CHEQUE = "cheque"
    TARJETA = "tarjeta"
    DEPOSITO = "deposito"
    OTRO = "otro"


# Método interno de los pagos que consumen saldo a favor (no se elige al registrar un cobro).
CREDIT_METHOD = "saldo_a_favor"


Reference = Annotated[
    Annotated[str, StringConstraints(max_length=100)] | None, BeforeValidator(clean_optional)
]
VoidReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class PaymentCreate(BaseModel):
    invoice_id: uuid.UUID
    amount: Amount
    method: PaymentMethod
    # Si no se informa, el servicio usa la fecha de hoy (Buenos Aires).
    payment_date: date | None = None
    reference: Reference = None
    # Si el importe supera el saldo, el excedente queda como saldo a favor del cliente.
    # Sin esta confirmación explícita, el sobrepago se rechaza (evita errores de tipeo).
    allow_credit: bool = False


class PaymentVoid(BaseModel):
    reason: VoidReason


class PaymentOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str
    client_id: uuid.UUID
    client_name: str
    payment_date: date
    # Importe imputado a la factura. Lo recibido = amount + credit_amount.
    amount: Decimal
    # Excedente que este cobro dejó como saldo a favor del cliente ("0.00" si no hubo).
    credit_amount: Decimal
    method: str
    reference: str | None
    is_void: bool
    void_reason: str | None
    voided_at: datetime | None
    created_by: uuid.UUID
    created_at: datetime
    # Saldo y estado actuales de la factura (tras registrar o anular, ya reflejan el cambio).
    invoice_balance: Decimal
    invoice_status: InvoiceStatus
