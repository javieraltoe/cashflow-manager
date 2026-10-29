import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import AdminUser, CurrentUser, DbSession, IdempotencyKey, Today
from app.schemas.common import Page, Pagination, pagination_params
from app.schemas.payment import (
    CREDIT_METHOD,
    PaymentCreate,
    PaymentMethod,
    PaymentOut,
    PaymentVoid,
)
from app.services import payments as payments_service

router = APIRouter(prefix="/payments", tags=["payments"])

PaymentSort = Literal[
    "payment_date", "-payment_date", "amount", "-amount", "created_at", "-created_at",
]  # fmt: skip


def payment_filters(
    invoice_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    method: PaymentMethod | Literal[CREDIT_METHOD] | None = None,  # type: ignore[valid-type]
    include_void: bool = False,
) -> payments_service.PaymentFilters:
    return payments_service.PaymentFilters(
        invoice_id=invoice_id,
        client_id=client_id,
        date_from=date_from,
        date_to=date_to,
        method=str(method) if method else None,
        include_void=include_void,
    )


@router.get("", response_model=Page[PaymentOut])
def list_payments(
    db: DbSession,
    _: CurrentUser,
    today: Today,
    filters: Annotated[payments_service.PaymentFilters, Depends(payment_filters)],
    pagination: Annotated[Pagination, Depends(pagination_params)],
    sort: PaymentSort = "-payment_date",
) -> Page[PaymentOut]:
    items, total = payments_service.list_payments(db, filters, pagination, today, sort)
    return Page[PaymentOut](
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.post(
    "",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": PaymentOut, "description": "Reintento: pago ya registrado"}},
)
def create_payment(
    data: PaymentCreate,
    db: DbSession,
    user: CurrentUser,
    today: Today,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> PaymentOut:
    """Registrar un cobro parcial o total.

    Si supera el saldo, se rechaza salvo `allow_credit: true`: en ese caso se imputa el saldo
    y el excedente queda como saldo a favor del cliente (`credit_amount`).
    """
    payment, replayed = payments_service.create_payment(db, data, user, today, idempotency_key)
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, db: DbSession, _: CurrentUser, today: Today) -> PaymentOut:
    return payments_service.get_payment(db, payment_id, today)


@router.post("/{payment_id}/void", response_model=PaymentOut)
def void_payment(
    payment_id: uuid.UUID, data: PaymentVoid, db: DbSession, user: AdminUser, today: Today
) -> PaymentOut:
    """Anulación lógica con motivo obligatorio (solo administrador, no se puede revertir)."""
    return payments_service.void_payment(db, payment_id, data, user, today)
