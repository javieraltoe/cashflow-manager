import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from app.schemas.common import clean_optional
from app.services.invoice_rules import InvoiceStatus

# Montos: Decimal con 2 decimales y hasta 15 dígitos (NUMERIC(15,2)). Nunca float.
# En las respuestas JSON viajan como string ("125000.50") para no perder precisión.
Amount = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]
InvoiceNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]
Description = Annotated[
    Annotated[str, StringConstraints(max_length=1000)] | None, BeforeValidator(clean_optional)
]


class InvoiceCreate(BaseModel):
    client_id: uuid.UUID
    invoice_number: InvoiceNumber
    issue_date: date
    due_date: date
    amount: Amount
    currency: Literal["ARS"] = "ARS"
    description: Description = None

    @field_validator("due_date")
    @classmethod
    def _due_after_issue(cls, v: date, info: ValidationInfo) -> date:
        issue = info.data.get("issue_date")
        if issue is not None and v < issue:
            raise ValueError("El vencimiento no puede ser anterior a la emisión")
        return v


class InvoiceUpdate(BaseModel):
    invoice_number: InvoiceNumber | None = None
    issue_date: date | None = None
    due_date: date | None = None
    amount: Amount | None = None
    description: Description = None
    # Anulación lógica (solo administrador; no se puede revertir).
    is_void: Literal[True] | None = None


class InvoiceOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    invoice_number: str
    issue_date: date
    due_date: date
    amount: Decimal
    currency: str
    description: str | None
    is_void: bool
    paid_amount: Decimal
    balance: Decimal
    status: InvoiceStatus
    days_overdue: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
