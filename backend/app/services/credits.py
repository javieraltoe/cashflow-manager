"""Saldo a favor del cliente (ADR-0003 #6): cobros a cuenta, anulación y consultas.

Los créditos nacen del excedente de un pago (lo crea services/payments.py) o de un cobro
a cuenta sin factura (create_on_account). Se consumen con pagos "saldo_a_favor"
(payments.apply_credit). El disponible nunca puede quedar negativo: toda operación que lo
mueve bloquea antes la fila del CLIENTE (orden de bloqueo: cliente → factura → pago).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import status
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.timeutils import utcnow
from app.models import Client, ClientCredit, Invoice, Payment, User
from app.schemas.common import Pagination
from app.schemas.credit import ClientCreditBalance, CreditCreate, CreditOut
from app.schemas.payment import CREDIT_METHOD, PaymentVoid
from app.services import audit
from app.services.clients import get_client
from app.services.invoice_rules import money


@dataclass
class CreditFilters:
    client_id: uuid.UUID | None = None
    include_void: bool = False


# ---------- Saldo disponible ----------


def lock_client(db: Session, client_id: uuid.UUID) -> Client | None:
    return db.scalar(select(Client).where(Client.id == client_id).with_for_update())


def get_balance(db: Session, client_id: uuid.UUID) -> ClientCreditBalance:
    credited = db.scalar(
        select(func.coalesce(func.sum(ClientCredit.amount), 0)).where(
            ClientCredit.client_id == client_id, ClientCredit.is_void.is_(False)
        )
    )
    applied = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0))
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(
            Invoice.client_id == client_id,
            Payment.method == CREDIT_METHOD,
            Payment.is_void.is_(False),
        )
    )
    credited, applied = money(credited or 0), money(applied or 0)
    return ClientCreditBalance(
        client_id=client_id, credited=credited, applied=applied, available=credited - applied
    )


def available(db: Session, client_id: uuid.UUID) -> Decimal:
    return get_balance(db, client_id).available


def client_balance(db: Session, client_id: uuid.UUID) -> ClientCreditBalance:
    get_client(db, client_id)  # 404 si no existe
    return get_balance(db, client_id)


# ---------- Consultas ----------


def _base_query() -> Select:
    return select(ClientCredit, Client.name.label("client_name")).join(
        Client, Client.id == ClientCredit.client_id
    )


def to_out(db: Session, credit: ClientCredit, client_name: str) -> CreditOut:
    return CreditOut(
        id=credit.id,
        client_id=credit.client_id,
        client_name=client_name,
        origin="excedente" if credit.payment_id else "a_cuenta",
        payment_id=credit.payment_id,
        credit_date=credit.credit_date,
        amount=money(credit.amount),
        method=credit.method,
        reference=credit.reference,
        is_void=credit.is_void,
        void_reason=credit.void_reason,
        voided_at=credit.voided_at,
        created_by=credit.created_by,
        created_at=credit.created_at,
        client_available=available(db, credit.client_id),
    )


def list_credits(
    db: Session, filters: CreditFilters, pagination: Pagination
) -> tuple[list[CreditOut], int]:
    stmt = _base_query()
    if filters.client_id:
        stmt = stmt.where(ClientCredit.client_id == filters.client_id)
    if not filters.include_void:
        stmt = stmt.where(ClientCredit.is_void.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(ClientCredit.credit_date.desc(), ClientCredit.id)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    ).all()
    return [to_out(db, r.ClientCredit, r.client_name) for r in rows], total


def get_credit(db: Session, credit_id: uuid.UUID) -> CreditOut:
    row = db.execute(_base_query().where(ClientCredit.id == credit_id)).first()
    if row is None:
        raise _not_found()
    return to_out(db, row.ClientCredit, row.client_name)


# ---------- Cobro a cuenta y anulación ----------


def _not_found() -> AppError:
    return AppError("credit_not_found", "Saldo a favor inexistente", status.HTTP_404_NOT_FOUND)


def _replay(db: Session, key: uuid.UUID | None, data: CreditCreate) -> CreditOut | None:
    if key is None:
        return None
    existing = db.scalar(select(ClientCredit).where(ClientCredit.idempotency_key == key))
    if existing is None:
        return None
    same = (
        existing.payment_id is None
        and existing.client_id == data.client_id
        and existing.amount == data.amount
        and existing.method == data.method.value
        and existing.reference == data.reference
        and (data.payment_date is None or existing.credit_date == data.payment_date)
    )
    db.rollback()  # libera el bloqueo del cliente
    if not same:
        raise AppError(
            "idempotency_key_reused",
            "La clave Idempotency-Key ya se usó para otra operación",
            status.HTTP_409_CONFLICT,
        )
    return get_credit(db, existing.id)


def create_on_account(
    db: Session,
    data: CreditCreate,
    actor: User,
    today: date,
    idempotency_key: uuid.UUID | None = None,
) -> tuple[CreditOut, bool]:
    """Cobro a cuenta (anticipo sin factura). Devuelve (crédito, repetido)."""
    credit_date = data.payment_date or today
    if credit_date > today:
        raise AppError(
            "validation_error",
            "La fecha de pago no puede ser posterior a hoy",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "payment_date",
        )
    client = lock_client(db, data.client_id)
    if client is None:
        raise AppError(
            "client_not_found", "Cliente inexistente", status.HTTP_404_NOT_FOUND, "client_id"
        )
    if (replayed := _replay(db, idempotency_key, data)) is not None:
        return replayed, True
    if not client.is_active:
        db.rollback()
        raise AppError(
            "client_inactive",
            "No se pueden registrar cobros a cuenta de un cliente inactivo",
            status.HTTP_409_CONFLICT,
            "client_id",
        )

    credit = ClientCredit(
        id=uuid.uuid4(),
        client_id=client.id,
        credit_date=credit_date,
        amount=data.amount,
        method=data.method.value,
        reference=data.reference,
        created_by=actor.id,
        idempotency_key=idempotency_key,
    )
    db.add(credit)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if (replayed := _replay(db, idempotency_key, data)) is not None:
            return replayed, True
        raise
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="credit",
        entity_id=credit.id,
        action="create",
        details={
            "client_id": client.id,
            "origin": "a_cuenta",
            "credit_date": credit_date,
            "amount": data.amount,
            "method": data.method,
            "reference": data.reference,
        },
    )
    db.commit()
    return get_credit(db, credit.id), False


def check_can_remove(db: Session, client_id: uuid.UUID, amount: Decimal) -> None:
    """Quitar `amount` de crédito no puede dejar el disponible negativo (ya imputado)."""
    disponible = available(db, client_id)
    if amount > disponible:
        db.rollback()
        raise AppError(
            "credit_in_use",
            f"El saldo a favor ya se imputó a facturas (disponible: {disponible}). "
            "Anulá primero esos pagos con saldo a favor.",
            status.HTTP_409_CONFLICT,
        )


def void_credit(db: Session, credit_id: uuid.UUID, data: PaymentVoid, actor: User) -> CreditOut:
    """Anula un cobro a cuenta (solo administrador, lo controla el router)."""
    client_id = db.scalar(select(ClientCredit.client_id).where(ClientCredit.id == credit_id))
    if client_id is None:
        raise _not_found()
    lock_client(db, client_id)
    credit = db.scalar(select(ClientCredit).where(ClientCredit.id == credit_id).with_for_update())
    if credit.payment_id is not None:
        db.rollback()
        raise AppError(
            "credit_from_payment",
            "Este saldo a favor es el excedente de un pago: anulá el pago que lo originó",
            status.HTTP_409_CONFLICT,
        )
    if credit.is_void:
        db.rollback()
        raise AppError(
            "credit_already_void", "El saldo a favor ya está anulado", status.HTTP_409_CONFLICT
        )
    check_can_remove(db, client_id, credit.amount)

    credit.is_void = True
    credit.void_reason = data.reason
    credit.voided_at = utcnow()
    db.flush()
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="credit",
        entity_id=credit.id,
        action="void",
        details={"client_id": client_id, "amount": credit.amount, "reason": data.reason},
    )
    db.commit()
    return get_credit(db, credit.id)
