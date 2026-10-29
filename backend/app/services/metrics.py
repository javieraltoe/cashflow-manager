"""Indicadores del dashboard (spec §6), calculados con agregaciones en SQL.

Convenciones:
- STOCK (saldo por cobrar, vencido, aging, deudores, próximos vencimientos): "a hoy",
  con la fecha local de Buenos Aires. No dependen del período elegido.
- FLUJO (cobrado, serie mensual): dependen del período [date_from, date_to].
- Cobrado = pagos vigentes con método distinto de "saldo_a_favor" + saldo a favor
  recibido vigente (excedentes y cobros a cuenta), por su fecha (ADR-0003 #18). Así cada
  peso que entró se cuenta una sola vez.
- Facturas anuladas y pagos/créditos anulados no cuentan nunca.
- Todo filtro por cliente se aplica a todos los indicadores.
"""

import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Select, and_, case, func, literal, select
from sqlalchemy.orm import Session

from app.models import Client, ClientCredit, Invoice, Payment
from app.schemas.invoice import InvoiceOut
from app.schemas.metrics import (
    Aging,
    AgingBucket,
    CollectionsMonthly,
    Debtor,
    MonthlyPoint,
    Overview,
    Period,
    TopDebtors,
    Upcoming,
)
from app.schemas.payment import CREDIT_METHOD
from app.services.invoice_rules import AGING_BUCKETS, InvoiceStatus, money
from app.services.invoices import _base_query, paid_subquery, to_out

DUE_SOON_DAYS = 7
UPCOMING_LIMIT = 200
ZERO = Decimal("0.00")


def _balances(client_id: uuid.UUID | None = None):
    """Subconsulta: saldo pendiente por factura vigente (importe − pagos vigentes)."""
    paid_sq = paid_subquery()
    balance = Invoice.amount - func.coalesce(paid_sq.c.paid, 0)
    stmt = (
        select(
            Invoice.id.label("invoice_id"),
            Invoice.client_id.label("client_id"),
            Invoice.due_date.label("due_date"),
            balance.label("balance"),
        )
        .outerjoin(paid_sq, paid_sq.c.invoice_id == Invoice.id)
        .where(Invoice.is_void.is_(False))
    )
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    return stmt.subquery("balances")


def _sum(expr):
    return func.coalesce(func.sum(expr), 0)


def _collected_payments(db: Session, period: Period, client_id: uuid.UUID | None) -> Decimal:
    stmt = select(_sum(Payment.amount)).where(
        Payment.is_void.is_(False),
        Payment.method != CREDIT_METHOD,
        Payment.payment_date.between(period.date_from, period.date_to),
    )
    if client_id is not None:
        stmt = stmt.join(Invoice, Invoice.id == Payment.invoice_id).where(
            Invoice.client_id == client_id
        )
    return money(db.scalar(stmt) or 0)


def _collected_credits(db: Session, period: Period, client_id: uuid.UUID | None) -> Decimal:
    stmt = select(_sum(ClientCredit.amount)).where(
        ClientCredit.is_void.is_(False),
        ClientCredit.credit_date.between(period.date_from, period.date_to),
    )
    if client_id is not None:
        stmt = stmt.where(ClientCredit.client_id == client_id)
    return money(db.scalar(stmt) or 0)


def _credit_available(db: Session, client_id: uuid.UUID | None) -> Decimal:
    credited = select(_sum(ClientCredit.amount)).where(ClientCredit.is_void.is_(False))
    applied = (
        select(_sum(Payment.amount))
        .join(Invoice, Invoice.id == Payment.invoice_id)
        .where(Payment.is_void.is_(False), Payment.method == CREDIT_METHOD)
    )
    if client_id is not None:
        credited = credited.where(ClientCredit.client_id == client_id)
        applied = applied.where(Invoice.client_id == client_id)
    return money(db.scalar(credited) or 0) - money(db.scalar(applied) or 0)


def overview(
    db: Session, today: date, period: Period, client_id: uuid.UUID | None = None
) -> Overview:
    b = _balances(client_id)
    overdue = and_(b.c.due_date < today, b.c.balance > 0)
    soon = and_(
        b.c.due_date >= today,
        b.c.due_date <= today + timedelta(days=DUE_SOON_DAYS),
        b.c.balance > 0,
    )
    row = db.execute(
        select(
            _sum(b.c.balance).label("total"),
            func.coalesce(func.sum(b.c.balance).filter(overdue), 0).label("overdue"),
            func.count().filter(overdue).label("overdue_count"),
            func.coalesce(func.sum(b.c.balance).filter(soon), 0).label("soon"),
            func.count().filter(soon).label("soon_count"),
        )
    ).one()
    total, overdue_balance = money(row.total), money(row.overdue)
    pct = None
    if total > 0:
        pct = (overdue_balance / total * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    payments = _collected_payments(db, period, client_id)
    credits = _collected_credits(db, period, client_id)
    return Overview(
        as_of=today,
        client_id=client_id,
        total_receivable=total,
        overdue_balance=overdue_balance,
        overdue_pct=pct,
        overdue_count=row.overdue_count,
        due_soon_days=DUE_SOON_DAYS,
        due_soon_balance=money(row.soon),
        due_soon_count=row.soon_count,
        credit_available=_credit_available(db, client_id),
        period=period,
        collected=payments + credits,
        collected_payments=payments,
        collected_credits=credits,
    )


def months_between(date_from: date, date_to: date) -> list[str]:
    """['2026-01', '2026-02', ...] incluyendo ambos extremos."""
    months, y, m = [], date_from.year, date_from.month
    while (y, m) <= (date_to.year, date_to.month):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def collections_monthly(
    db: Session, period: Period, client_id: uuid.UUID | None = None
) -> CollectionsMonthly:
    pay_month = func.to_char(Payment.payment_date, "YYYY-MM")
    pay = select(pay_month.label("month"), _sum(Payment.amount).label("amount")).where(
        Payment.is_void.is_(False),
        Payment.method != CREDIT_METHOD,
        Payment.payment_date.between(period.date_from, period.date_to),
    )
    if client_id is not None:
        pay = pay.join(Invoice, Invoice.id == Payment.invoice_id).where(
            Invoice.client_id == client_id
        )
    cred_month = func.to_char(ClientCredit.credit_date, "YYYY-MM")
    cred = select(cred_month.label("month"), _sum(ClientCredit.amount).label("amount")).where(
        ClientCredit.is_void.is_(False),
        ClientCredit.credit_date.between(period.date_from, period.date_to),
    )
    if client_id is not None:
        cred = cred.where(ClientCredit.client_id == client_id)

    payments = {r.month: money(r.amount) for r in db.execute(pay.group_by(pay_month))}
    credits = {r.month: money(r.amount) for r in db.execute(cred.group_by(cred_month))}
    items = []
    for month in months_between(period.date_from, period.date_to):
        p, c = payments.get(month, ZERO), credits.get(month, ZERO)
        items.append(MonthlyPoint(month=month, collected=p + c, payments=p, credits=c))
    return CollectionsMonthly(
        period=period,
        client_id=client_id,
        total=sum((i.collected for i in items), ZERO),
        items=items,
    )


def aging(db: Session, today: date, client_id: uuid.UUID | None = None) -> Aging:
    b = _balances(client_id)
    # Rangos por días de mora = hoy − vencimiento (1–30, 31–60, 61–90, 91+).
    whens = [
        (b.c.due_date >= today - timedelta(days=high), literal(label))
        for label, _low, high in AGING_BUCKETS
        if high is not None
    ]
    bucket = case(*whens, else_=literal(AGING_BUCKETS[-1][0])).label("bucket")
    rows = db.execute(
        select(bucket, _sum(b.c.balance).label("balance"), func.count().label("count"))
        .where(b.c.due_date < today, b.c.balance > 0)
        .group_by(bucket)
    ).all()
    found = {r.bucket: r for r in rows}
    items = [
        AgingBucket(
            bucket=label,
            balance=money(found[label].balance) if label in found else ZERO,
            count=found[label].count if label in found else 0,
        )
        for label, _low, _high in AGING_BUCKETS
    ]
    return Aging(
        as_of=today,
        client_id=client_id,
        total_overdue=sum((i.balance for i in items), ZERO),
        items=items,
    )


def top_debtors(
    db: Session, today: date, limit: int = 10, client_id: uuid.UUID | None = None
) -> TopDebtors:
    b = _balances(client_id)
    total = _sum(b.c.balance)
    overdue = func.coalesce(func.sum(b.c.balance).filter(b.c.due_date < today), 0)
    rows = db.execute(
        select(
            Client.id,
            Client.name,
            total.label("balance"),
            overdue.label("overdue"),
            func.count().label("invoices"),
        )
        .join(Client, Client.id == b.c.client_id)
        .where(b.c.balance > 0)
        .group_by(Client.id, Client.name)
        .order_by(total.desc(), func.lower(Client.name))
        .limit(limit)
    ).all()
    return TopDebtors(
        as_of=today,
        items=[
            Debtor(
                client_id=r.id,
                client_name=r.name,
                balance=money(r.balance),
                overdue_balance=money(r.overdue),
                invoice_count=r.invoices,
            )
            for r in rows
        ],
    )


def upcoming_query(today: date, days: int, client_id: uuid.UUID | None) -> Select:
    stmt = _base_query(today)
    status = stmt.selected_columns.status
    stmt = stmt.where(
        Invoice.is_void.is_(False),
        status.in_([InvoiceStatus.PENDIENTE.value, InvoiceStatus.PARCIAL.value]),
        Invoice.due_date.between(today, today + timedelta(days=days)),
    )
    if client_id is not None:
        stmt = stmt.where(Invoice.client_id == client_id)
    return stmt


def upcoming(
    db: Session, today: date, days: int = DUE_SOON_DAYS, client_id: uuid.UUID | None = None
) -> Upcoming:
    stmt = upcoming_query(today, days, client_id)
    agg = stmt.subquery()
    count, total = db.execute(select(func.count(), _sum(agg.c.amount - agg.c.paid))).one()
    rows = db.execute(
        stmt.order_by(Invoice.due_date, Invoice.invoice_number).limit(UPCOMING_LIMIT)
    ).all()
    items: list[InvoiceOut] = [to_out(r.Invoice, r.client_name, r.paid, today) for r in rows]
    return Upcoming(
        as_of=today,
        days=days,
        client_id=client_id,
        total_balance=money(total or 0),
        count=count,
        items=items,
    )
