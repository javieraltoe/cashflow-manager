"""Servicio de facturas: alta, edición, anulación y consultas con saldo y estado.

El saldo y el estado NO se guardan: se calculan siempre a partir de los pagos vigentes
y de la fecha local de hoy, por eso una factura pasa a VENCIDA sola (HU05).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import status
from sqlalchemy import Select, case, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Client, Invoice, Payment, Role, User
from app.schemas.common import Pagination
from app.schemas.invoice import InvoiceCreate, InvoiceOut, InvoiceUpdate
from app.services import audit
from app.services.clients import get_client, like_pattern
from app.services.invoice_rules import (
    InvoiceStatus,
    balance,
    compute_status,
    days_overdue,
    money,
)

SORTS = {
    "due_date": Invoice.due_date.asc(),
    "-due_date": Invoice.due_date.desc(),
    "issue_date": Invoice.issue_date.asc(),
    "-issue_date": Invoice.issue_date.desc(),
    "amount": Invoice.amount.asc(),
    "-amount": Invoice.amount.desc(),
    "invoice_number": Invoice.invoice_number.asc(),
    "-invoice_number": Invoice.invoice_number.desc(),
    "created_at": Invoice.created_at.asc(),
    "-created_at": Invoice.created_at.desc(),
}


@dataclass
class InvoiceFilters:
    client_id: uuid.UUID | None = None
    status: InvoiceStatus | None = None
    issue_from: date | None = None
    issue_to: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    q: str | None = None
    include_void: bool = False


# ---------- Expresiones SQL de saldo y estado ----------


def paid_subquery():
    """Suma de pagos vigentes (no anulados) por factura."""
    return (
        select(Payment.invoice_id, func.sum(Payment.amount).label("paid"))
        .where(Payment.is_void.is_(False))
        .group_by(Payment.invoice_id)
        .subquery("paid_by_invoice")
    )


def status_expression(amount, paid, due_date, is_void, today: date):
    """Mismo criterio que invoice_rules.compute_status, en SQL (para filtrar)."""
    saldo = amount - paid
    return case(
        (is_void.is_(True), literal(InvoiceStatus.ANULADA.value)),
        (saldo <= 0, literal(InvoiceStatus.PAGADA.value)),
        (due_date < today, literal(InvoiceStatus.VENCIDA.value)),
        (saldo < amount, literal(InvoiceStatus.PARCIAL.value)),
        else_=literal(InvoiceStatus.PENDIENTE.value),
    )


def _base_query(today: date) -> Select:
    paid_sq = paid_subquery()
    paid = func.coalesce(paid_sq.c.paid, 0)
    st = status_expression(Invoice.amount, paid, Invoice.due_date, Invoice.is_void, today)
    return (
        select(Invoice, Client.name.label("client_name"), paid.label("paid"), st.label("status"))
        .join(Client, Client.id == Invoice.client_id)
        .outerjoin(paid_sq, paid_sq.c.invoice_id == Invoice.id)
    )


def to_out(invoice: Invoice, client_name: str, paid: Decimal, today: date) -> InvoiceOut:
    paid = money(paid)
    saldo = balance(invoice.amount, paid)
    st = compute_status(invoice.amount, paid, invoice.due_date, today, invoice.is_void)
    return InvoiceOut(
        id=invoice.id,
        client_id=invoice.client_id,
        client_name=client_name,
        invoice_number=invoice.invoice_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        amount=money(invoice.amount),
        currency=invoice.currency,
        description=invoice.description,
        is_void=invoice.is_void,
        paid_amount=paid,
        balance=saldo,
        status=st,
        days_overdue=0 if invoice.is_void else days_overdue(saldo, invoice.due_date, today),
        created_by=invoice.created_by,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


# ---------- Consultas ----------


def filtered_query(filters: InvoiceFilters, today: date) -> Select:
    """Consulta de facturas con los filtros del listado (la usa también la exportación)."""
    stmt = _base_query(today)
    st_col = stmt.selected_columns.status

    if filters.client_id:
        stmt = stmt.where(Invoice.client_id == filters.client_id)
    if filters.issue_from:
        stmt = stmt.where(Invoice.issue_date >= filters.issue_from)
    if filters.issue_to:
        stmt = stmt.where(Invoice.issue_date <= filters.issue_to)
    if filters.due_from:
        stmt = stmt.where(Invoice.due_date >= filters.due_from)
    if filters.due_to:
        stmt = stmt.where(Invoice.due_date <= filters.due_to)
    if filters.q and filters.q.strip():
        stmt = stmt.where(Invoice.invoice_number.ilike(like_pattern(filters.q), escape="\\"))
    if filters.status:
        stmt = stmt.where(st_col == filters.status.value)
    if not filters.include_void and filters.status != InvoiceStatus.ANULADA:
        stmt = stmt.where(Invoice.is_void.is_(False))
    return stmt


def list_invoices(
    db: Session,
    filters: InvoiceFilters,
    pagination: Pagination,
    today: date,
    sort: str = "due_date",
) -> tuple[list[InvoiceOut], int]:
    stmt = filtered_query(filters, today)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(SORTS[sort], Invoice.id).offset(pagination.offset).limit(pagination.page_size)
    ).all()
    return [to_out(r.Invoice, r.client_name, r.paid, today) for r in rows], total


def get_invoice(db: Session, invoice_id: uuid.UUID, today: date) -> InvoiceOut:
    row = db.execute(_base_query(today).where(Invoice.id == invoice_id)).first()
    if row is None:
        raise _not_found()
    return to_out(row.Invoice, row.client_name, row.paid, today)


def paid_total(db: Session, invoice_id: uuid.UUID) -> Decimal:
    value = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.invoice_id == invoice_id, Payment.is_void.is_(False)
        )
    )
    return money(value or 0)


# ---------- Altas y modificaciones ----------


def _not_found() -> AppError:
    return AppError("invoice_not_found", "Factura inexistente", status.HTTP_404_NOT_FOUND)


def _duplicate() -> AppError:
    return AppError(
        "duplicate_invoice_number",
        "Ya existe una factura con ese número para este cliente",
        status.HTTP_409_CONFLICT,
        "invoice_number",
    )


def _check_number_free(
    db: Session, client_id: uuid.UUID, number: str, exclude_id: uuid.UUID | None = None
) -> None:
    stmt = select(Invoice.id).where(
        Invoice.client_id == client_id, Invoice.invoice_number == number
    )
    if exclude_id is not None:
        stmt = stmt.where(Invoice.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise _duplicate()


def create_invoice(db: Session, data: InvoiceCreate, actor: User, today: date) -> InvoiceOut:
    try:
        client = get_client(db, data.client_id)
    except AppError as exc:
        exc.field = "client_id"
        raise
    if not client.is_active:
        raise AppError(
            "client_inactive",
            "No se pueden cargar facturas a un cliente inactivo",
            status.HTTP_409_CONFLICT,
            "client_id",
        )
    _check_number_free(db, client.id, data.invoice_number)

    invoice = Invoice(id=uuid.uuid4(), created_by=actor.id, **data.model_dump())
    db.add(invoice)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="create",
        details=data.model_dump(),
    )
    db.commit()
    return get_invoice(db, invoice.id, today)


def update_invoice(
    db: Session, invoice_id: uuid.UUID, data: InvoiceUpdate, actor: User, today: date
) -> InvoiceOut:
    # Bloqueo de la fila: evita carreras con el registro de pagos (ver services/payments.py).
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
    if invoice is None:
        raise _not_found()
    if invoice.is_void:
        raise AppError(
            "invoice_void",
            "La factura está anulada y no se puede modificar",
            status.HTTP_409_CONFLICT,
        )

    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if "description" in data.model_fields_set and data.description is None:
        changes["description"] = None  # permite borrar la descripción

    if changes.get("is_void"):
        if actor.role != Role.ADMIN:
            raise AppError(
                "forbidden",
                "Solo un administrador puede anular facturas",
                status.HTTP_403_FORBIDDEN,
            )
        if paid_total(db, invoice.id) > 0:
            raise AppError(
                "invoice_has_payments",
                "Anulá primero los pagos vigentes de la factura",
                status.HTTP_409_CONFLICT,
            )

    new_issue = changes.get("issue_date", invoice.issue_date)
    new_due = changes.get("due_date", invoice.due_date)
    if new_due < new_issue:
        raise AppError(
            "validation_error",
            "El vencimiento no puede ser anterior a la emisión",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "due_date",
        )
    if "amount" in changes and changes["amount"] < paid_total(db, invoice.id):
        raise AppError(
            "amount_below_paid",
            "El importe no puede ser menor a lo ya cobrado",
            status.HTTP_409_CONFLICT,
            "amount",
        )
    if "invoice_number" in changes:
        _check_number_free(db, invoice.client_id, changes["invoice_number"], invoice.id)

    details = audit.diff(invoice, changes)
    if not details:
        db.rollback()  # libera el bloqueo
        return get_invoice(db, invoice.id, today)
    for field, value in changes.items():
        setattr(invoice, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    audit.record(
        db,
        actor_id=actor.id,
        entity_type="invoice",
        entity_id=invoice.id,
        action="void" if changes.get("is_void") else "update",
        details=details,
    )
    db.commit()
    return get_invoice(db, invoice.id, today)
