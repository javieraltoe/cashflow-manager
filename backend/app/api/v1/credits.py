import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import AdminUser, CurrentUser, DbSession, IdempotencyKey, Today
from app.schemas.common import Page, Pagination, pagination_params
from app.schemas.credit import ClientCreditBalance, CreditApply, CreditCreate, CreditOut
from app.schemas.payment import PaymentOut, PaymentVoid
from app.services import credits as credits_service
from app.services import payments as payments_service

router = APIRouter(tags=["credits"])

_REPLAY = {200: {"description": "Reintento: operación ya registrada"}}


def _mark_replay(response: Response, replayed: bool) -> None:
    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"


@router.get("/clients/{client_id}/credit", response_model=ClientCreditBalance)
def get_client_credit(client_id: uuid.UUID, db: DbSession, _: CurrentUser) -> ClientCreditBalance:
    """Saldo a favor del cliente: acreditado, imputado y disponible."""
    return credits_service.client_balance(db, client_id)


@router.get("/credits", response_model=Page[CreditOut])
def list_credits(
    db: DbSession,
    _: CurrentUser,
    pagination: Annotated[Pagination, Depends(pagination_params)],
    client_id: uuid.UUID | None = None,
    include_void: bool = False,
) -> Page[CreditOut]:
    filters = credits_service.CreditFilters(client_id=client_id, include_void=include_void)
    items, total = credits_service.list_credits(db, filters, pagination)
    return Page[CreditOut](
        items=items, total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.post(
    "/credits", response_model=CreditOut, status_code=status.HTTP_201_CREATED, responses=_REPLAY
)
def create_on_account(
    data: CreditCreate,
    db: DbSession,
    user: CurrentUser,
    today: Today,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> CreditOut:
    """Cobro a cuenta (anticipo sin factura): todo el importe queda como saldo a favor."""
    credit, replayed = credits_service.create_on_account(db, data, user, today, idempotency_key)
    _mark_replay(response, replayed)
    return credit


@router.get("/credits/{credit_id}", response_model=CreditOut)
def get_credit(credit_id: uuid.UUID, db: DbSession, _: CurrentUser) -> CreditOut:
    return credits_service.get_credit(db, credit_id)


@router.post("/credits/{credit_id}/void", response_model=CreditOut)
def void_credit(
    credit_id: uuid.UUID, data: PaymentVoid, db: DbSession, user: AdminUser
) -> CreditOut:
    """Anular un cobro a cuenta (solo administrador; bloqueado si ya se imputó)."""
    return credits_service.void_credit(db, credit_id, data, user)


@router.post(
    "/credits/apply",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    responses=_REPLAY,
)
def apply_credit(
    data: CreditApply,
    db: DbSession,
    user: CurrentUser,
    today: Today,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> PaymentOut:
    """Imputar saldo a favor del cliente a una de sus facturas (pago "saldo_a_favor")."""
    payment, replayed = payments_service.apply_credit(db, data, user, today, idempotency_key)
    _mark_replay(response, replayed)
    return payment
