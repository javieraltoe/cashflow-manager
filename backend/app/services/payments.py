"""Servicio de pagos: registro (parcial o total), anulación lógica y consultas (HU04).

Concurrencia: toda operación bloquea con SELECT … FOR UPDATE, siempre en el orden
cliente → factura → pago (evita deadlocks). Con la factura bloqueada, dos cobros
simultáneos se serializan y nunca superan el importe; con el cliente bloqueado, el saldo
a favor disponible nunca queda negativo.

Saldo a favor (ADR-0003 #6): si el pago supera el saldo y el operador lo confirma
(allow_credit), se imputa a la factura solo el saldo y el excedente queda como crédito del
cliente (client_credits). El crédito se consume con apply_credit, que registra un pago con
método "saldo_a_favor".

Idempotencia: si el cliente manda Idempotency-Key, un reintento con la misma clave y los
mismos datos devuelve el pago ya registrado en lugar de duplicarlo.
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
from app.schemas.credit import CreditApply
from app.schemas.payment import CREDIT_METHOD, PaymentCreate, PaymentOut, PaymentVoid
from app.services import audit, credits
from app.services.invoice_rules import ZERO, balance, compute_status, money
from app.services.invoices import paid_subquery, paid_total

SORTS = {
    "payment_date": Payment.payment_date.asc(),
    "-payment_date": Payment.payment_date.desc(),
    "amount": Payment.amount.asc(),
    "-amount": Payment.amount.desc(),
    "created_at": Payment.created_at.asc(),
    "-created_at": Payment.created_at.desc(),
}


@dataclass
class PaymentFilters:
    invoice_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    method: str | None = None
    include_void: bool = False


# ---------- Consultas ----------


def _base_query() -> Select:
    paid_sq = paid_subquery()
    return (
        select(
            Payment,
            Invoice,
            Client.name.label("client_name"),
            func.coalesce(paid_sq.c.paid, 0).label("paid"),
            func.coalesce(ClientCredit.amount, 0).label("credit_amount"),
        )
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .join(Client, Client.id == Invoice.client_id)
        .outerjoin(paid_sq, paid_sq.c.invoice_id == Invoice.id)
        .outerjoin(ClientCredit, ClientCredit.payment_id == Payment.id)
    )


def to_out(
    payment: Payment,
    invoice: Invoice,
    client_name: str,
    paid: Decimal,
    credit_amount: Decimal,
    today: date,
) -> PaymentOut:
    paid = money(paid)
    return PaymentOut(
        id=payment.id,
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        client_id=invoice.client_id,
        client_name=client_name,
        payment_date=payment.payment_date,
        amount=money(payment.amount),
        credit_amount=money(credit_amount),
        method=payment.method,
        reference=payment.reference,
        is_void=payment.is_void,
        void_reason=payment.void_reason,
        voided_at=payment.voided_at,
        created_by=payment.created_by,
        created_at=payment.created_at,
        invoice_balance=balance(invoice.amount, paid),
        invoice_status=compute_status(
            invoice.amount, paid, invoice.due_date, today, invoice.is_void
        ),
    )


def _row_out(row, today: date) -> PaymentOut:
    return to_out(row.Payment, row.Invoice, row.client_name, row.paid, row.credit_amount, today)


def list_payments(
    db: Session,
    filters: PaymentFilters,
    pagination: Pagination,
    today: date,
    sort: str = "-payment_date",
) -> tuple[list[PaymentOut], int]:
    stmt = _base_query()
    if filters.invoice_id:
        stmt = stmt.where(Payment.invoice_id == filters.invoice_id)
    if filters.client_id:
        stmt = stmt.where(Invoice.client_id == filters.client_id)
    if filters.date_from:
        stmt = stmt.where(Payment.payment_date >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(Payment.payment_date <= filters.date_to)
    if filters.method:
        stmt = stmt.where(Payment.method == filters.method)
    if not filters.include_void:
        stmt = stmt.where(Payment.is_void.is_(False))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(SORTS[sort], Payment.id).offset(pagination.offset).limit(pagination.page_size)
    ).all()
    return [_row_out(r, today) for r in rows], total


def get_payment(db: Session, payment_id: uuid.UUID, today: date) -> PaymentOut:
    row = db.execute(_base_query().where(Payment.id == payment_id)).first()
    if row is None:
        raise _not_found()
    return _row_out(row, today)


# ---------- Validaciones comunes ----------


def _not_found() -> AppError:
    return AppError("payment_not_found", "Pago inexistente", status.HTTP_404_NOT_FOUND)


def _check_date(payment_date: date, today: date) -> None:
    if payment_date > today:
        raise AppError(
            "validation_error",
            "La fecha de pago no puede ser posterior a hoy",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "payment_date",
        )


def _lock_client_and_invoice(db: Session, invoice_id: uuid.UUID) -> Invoice:
    """Bloquea cliente → factura (en ese orden) y devuelve la factura."""
    client_id = db.scalar(select(Invoice.client_id).where(Invoice.id == invoice_id))
    if client_id is None:
        raise AppError(
            "invoice_not_found", "Factura inexistente", status.HTTP_404_NOT_FOUND, "invoice_id"
        )
    credits.lock_client(db, client_id)
    return db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())


def _check_invoice_open(db: Session, invoice: Invoice) -> Decimal:
    """Factura vigente y con saldo; devuelve el saldo (con la factura ya bloqueada)."""
    if invoice.is_void:
        db.rollback()  # libera los bloqueos
        raise AppError(
            "invoice_void",
            "La factura está anulada y no admite pagos",
            status.HTTP_409_CONFLICT,
            "invoice_id",
        )
    saldo = balance(invoice.amount, paid_total(db, invoice.id))
    if saldo <= ZERO:
        db.rollback()
        raise AppError(
            "invoice_already_paid", "La factura ya está totalmente pagada", status.HTTP_409_CONFLICT
        )
    return saldo


def _replay(
    db: Session,
    key: uuid.UUID | None,
    today: date,
    *,
    invoice_id: uuid.UUID,
    received: Decimal,
    method: str,
    reference: str | None = None,
    payment_date: date | None = None,
) -> PaymentOut | None:
    """Pago ya registrado con esa clave, o None. Misma clave con otros datos → 409."""
    if key is None:
        return None
    row = db.execute(_base_query().where(Payment.idempotency_key == key)).first()
    if row is None:
        return None
    existing = row.Payment
    same = (
        existing.invoice_id == invoice_id
        and existing.amount + row.credit_amount == received
        and existing.method == method
        and existing.reference == reference
        and (payment_date is None or existing.payment_date == payment_date)
    )
    db.rollback()  # libera los bloqueos
    if not same:
        raise AppError(
            "idempotency_key_reused",
            "La clave Idempotency-Key ya se usó para otro pago",
            status.HTTP_409_CONFLICT,
        )
    return get_payment(db, existing.id, today)


def _flush_or_replay(db: Session, replay) -> PaymentOut | None:
    """Flush; si choca la clave de idempotencia (otro request ganó la carrera), el repetido."""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if (replayed := replay()) is not None:
            return replayed
        raise
    return None


# ---------- Registro ----------


def create_payment(
    db: Session,
    data: PaymentCreate,
    actor: User,
    today: date,
    idempotency_key: uuid.UUID | None = None,
) -> tuple[PaymentOut, bool]:
    """Devuelve (pago, repetido). repetido=True si la clave ya existía y no se creó nada."""
    payment_date = data.payment_date or today
    _check_date(payment_date, today)

    def replay() -> PaymentOut | None:
        return _replay(
            db,
            idempotency_key,
            today,
            invoice_id=data.invoice_id,
            received=data.amount,
            method=data.method.value,
            reference=data.reference,
            payment_date=data.payment_date,
        )

    invoice = _lock_client_and_invoice(db, data.invoice_id)
    # Antes de las reglas de saldo: el reintento de un pago que saldó la factura no es un error.
    if (replayed := replay()) is not None:
        return replayed, True
    saldo = _check_invoice_open(db, invoice)

    excess = ZERO
    if data.amount > saldo:
        if not data.allow_credit:
            db.rollback()
            raise AppError(
                "amount_exceeds_balance",
                f"El pago supera el saldo pendiente ({saldo}). Para dejar el excedente "
                f"({data.amount - saldo}) como saldo a favor, confirmalo con allow_credit.",
                status.HTTP_409_CONFLICT,
                "amount",
            )
        excess = data.amount - saldo
    applied = data.amount - excess

    payment = Payment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        payment_date=payment_date,
        amount=applied,
        method=data.method.value,
        reference=data.reference,
        created_by=actor.id,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    if (replayed := _flush_or_replay(db, replay)) is not None:
        return replayed, True

    credit = None
    if excess > ZERO:
        credit = ClientCredit(
            id=uuid.uuid4(),
            client_id=invoice.client_id,
            payment_id=payment.id,
            credit_date=payment_date,
            amount=excess,
            method=data.method.value,
            reference=data.reference,
            created_by=actor.id,
        )
        db.add(credit)
        db.flush()
        audit.record(
            db,
            actor_id=actor.id,
            entity_type="credit",
            entity_id=credit.id,
            action="create",
            details={
                "client_id": invoice.client_id,
                "origin": "excedente",
                "payment_id": payment.id,
                "amount": excess,
            },
        )
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="payment",
        entity_id=payment.id,
        action="create",
        details={
            "invoice_id": invoice.id,
            "payment_date": payment_date,
            "received": data.amount,
            "amount": applied,
            "credit_amount": excess,
            "credit_id": credit.id if credit else None,
            "method": data.method,
            "reference": data.reference,
            "balance_before": saldo,
            "balance_after": saldo - applied,
        },
    )
    db.commit()
    return get_payment(db, payment.id, today), False


def apply_credit(
    db: Session,
    data: CreditApply,
    actor: User,
    today: date,
    idempotency_key: uuid.UUID | None = None,
) -> tuple[PaymentOut, bool]:
    """Imputa saldo a favor del cliente a una de sus facturas (pago "saldo_a_favor")."""

    def replay() -> PaymentOut | None:
        return _replay(
            db,
            idempotency_key,
            today,
            invoice_id=data.invoice_id,
            received=data.amount,
            method=CREDIT_METHOD,
        )

    invoice = _lock_client_and_invoice(db, data.invoice_id)
    if (replayed := replay()) is not None:
        return replayed, True
    saldo = _check_invoice_open(db, invoice)
    if data.amount > saldo:
        db.rollback()
        raise AppError(
            "amount_exceeds_balance",
            f"El importe supera el saldo pendiente de la factura ({saldo})",
            status.HTTP_409_CONFLICT,
            "amount",
        )
    disponible = credits.available(db, invoice.client_id)
    if data.amount > disponible:
        db.rollback()
        raise AppError(
            "insufficient_credit",
            f"El cliente no tiene saldo a favor suficiente (disponible: {disponible})",
            status.HTTP_409_CONFLICT,
            "amount",
        )

    payment = Payment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        payment_date=today,
        amount=data.amount,
        method=CREDIT_METHOD,
        created_by=actor.id,
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    if (replayed := _flush_or_replay(db, replay)) is not None:
        return replayed, True
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="payment",
        entity_id=payment.id,
        action="create",
        details={
            "invoice_id": invoice.id,
            "payment_date": today,
            "amount": data.amount,
            "method": CREDIT_METHOD,
            "balance_before": saldo,
            "balance_after": saldo - data.amount,
            "credit_available_after": disponible - data.amount,
        },
    )
    db.commit()
    return get_payment(db, payment.id, today), False


# ---------- Anulación ----------


def void_payment(
    db: Session, payment_id: uuid.UUID, data: PaymentVoid, actor: User, today: date
) -> PaymentOut:
    """Anulación lógica (solo administrador, lo controla el router). No se puede revertir.

    Si el pago dejó saldo a favor, se anula también ese crédito, salvo que ya se haya
    imputado a otras facturas (409 credit_in_use: hay que anular antes esas imputaciones).
    """
    invoice_id = db.scalar(select(Payment.invoice_id).where(Payment.id == payment_id))
    if invoice_id is None:
        raise _not_found()
    invoice = _lock_client_and_invoice(db, invoice_id)
    payment = db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment.is_void:
        db.rollback()
        raise AppError("payment_already_void", "El pago ya está anulado", status.HTTP_409_CONFLICT)

    credit = db.scalar(
        select(ClientCredit).where(ClientCredit.payment_id == payment.id).with_for_update()
    )
    now = utcnow()
    if credit is not None and not credit.is_void:
        credits.check_can_remove(db, invoice.client_id, credit.amount)
        credit.is_void = True
        credit.void_reason = data.reason
        credit.voided_at = now
        audit.record(
            db,
            actor_id=actor.id,
            entity_type="credit",
            entity_id=credit.id,
            action="void",
            details={"payment_id": payment.id, "amount": credit.amount, "reason": data.reason},
        )

    payment.is_void = True
    payment.void_reason = data.reason
    payment.voided_at = now
    db.flush()
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="payment",
        entity_id=payment.id,
        action="void",
        details={
            "invoice_id": invoice_id,
            "amount": payment.amount,
            "credit_amount": credit.amount if credit else ZERO,
            "reason": data.reason,
        },
    )
    db.commit()
    return get_payment(db, payment.id, today)
