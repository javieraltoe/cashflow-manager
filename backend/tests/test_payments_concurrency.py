"""Concurrencia de pagos (§16 multiusuario): dos cobros simultáneos sobre la misma factura.

A diferencia del resto, este test usa sesiones reales con COMMIT (dos conexiones
compitiendo por la misma fila), así que crea sus propios datos y los borra al final.
"""

import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import AuditEvent, Client, ClientCredit, Invoice, Payment, Role, User
from app.schemas.credit import CreditApply
from app.schemas.payment import PaymentCreate, PaymentMethod
from app.services import payments as payments_service
from tests.helpers import make_user

pytestmark = pytest.mark.integration

HOY = date(2026, 10, 28)


@pytest.fixture
def factura_comprometida(database):
    """Usuario, cliente y factura de $1000 confirmados (visibles para otras sesiones)."""
    tag = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        user = make_user(db, f"concurrencia-{tag}@demo.com.ar", Role.OPERATOR)
        client = Client(name=f"Concurrencia {tag}")
        db.add(client)
        db.flush()
        invoice = Invoice(
            client_id=client.id,
            invoice_number=f"C-{tag}",
            issue_date=date(2026, 10, 1),
            due_date=date(2026, 10, 30),
            amount=Decimal("1000.00"),
            created_by=user.id,
        )
        db.add(invoice)
        db.commit()
        ids = (user.id, client.id, invoice.id)
    yield ids
    user_id, client_id, invoice_id = ids
    with SessionLocal() as db:
        db.execute(delete(AuditEvent).where(AuditEvent.actor_user_id == user_id))
        db.execute(delete(ClientCredit).where(ClientCredit.client_id == client_id))
        invoices = select(Invoice.id).where(Invoice.client_id == client_id)
        db.execute(delete(Payment).where(Payment.invoice_id.in_(invoices)))
        db.execute(delete(Invoice).where(Invoice.client_id == client_id))
        db.execute(delete(Client).where(Client.id == client_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()


def test_dos_pagos_simultaneos_no_superan_el_importe(factura_comprometida):
    user_id, _, invoice_id = factura_comprometida
    data = PaymentCreate(
        invoice_id=invoice_id, amount=Decimal("1000.00"), method=PaymentMethod.EFECTIVO
    )
    barrier = threading.Barrier(2)
    results: list[str] = []

    def pagar() -> None:
        with SessionLocal() as db:
            actor = db.get(User, user_id)
            barrier.wait()
            try:
                payments_service.create_payment(db, data, actor, HOY)
                results.append("ok")
            except AppError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=pagar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == ["invoice_already_paid", "ok"]
    with SessionLocal() as db:
        cobrado = db.scalar(
            select(func.sum(Payment.amount)).where(
                Payment.invoice_id == invoice_id, Payment.is_void.is_(False)
            )
        )
    assert cobrado == Decimal("1000.00")


def test_doble_envio_simultaneo_con_la_misma_clave(factura_comprometida):
    """Doble clic: dos requests idénticos a la vez con la misma Idempotency-Key → un solo pago."""
    user_id, _, invoice_id = factura_comprometida
    data = PaymentCreate(
        invoice_id=invoice_id, amount=Decimal("300.00"), method=PaymentMethod.EFECTIVO
    )
    key = uuid.uuid4()
    barrier = threading.Barrier(2)
    results: list[tuple[uuid.UUID, bool]] = []

    def pagar() -> None:
        with SessionLocal() as db:
            actor = db.get(User, user_id)
            barrier.wait()
            payment, replayed = payments_service.create_payment(db, data, actor, HOY, key)
            results.append((payment.id, replayed))

    threads = [threading.Thread(target=pagar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == 2
    assert results[0][0] == results[1][0]  # el mismo pago
    assert sorted(r[1] for r in results) == [False, True]
    with SessionLocal() as db:
        cantidad = db.scalar(select(func.count()).where(Payment.invoice_id == invoice_id))
    assert cantidad == 1


def test_dos_imputaciones_simultaneas_no_gastan_dos_veces_el_credito(factura_comprometida):
    """Mismo saldo a favor de $1000 imputado a la vez a dos facturas: solo una lo consigue."""
    user_id, client_id, invoice_id = factura_comprometida
    with SessionLocal() as db:
        otra = Invoice(
            client_id=client_id,
            invoice_number=f"C2-{uuid.uuid4().hex[:8]}",
            issue_date=date(2026, 10, 1),
            due_date=date(2026, 10, 30),
            amount=Decimal("1000.00"),
            created_by=user_id,
        )
        db.add(otra)
        db.add(
            ClientCredit(
                client_id=client_id,
                credit_date=HOY,
                amount=Decimal("1000.00"),
                method="efectivo",
                created_by=user_id,
            )
        )
        db.commit()
        otra_id = otra.id

    barrier = threading.Barrier(2)
    results: list[str] = []

    def imputar(target: uuid.UUID) -> None:
        with SessionLocal() as db:
            actor = db.get(User, user_id)
            barrier.wait()
            try:
                payments_service.apply_credit(
                    db, CreditApply(invoice_id=target, amount=Decimal("1000.00")), actor, HOY
                )
                results.append("ok")
            except AppError as exc:
                results.append(exc.code)

    threads = [threading.Thread(target=imputar, args=(t,)) for t in (invoice_id, otra_id)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(results) == ["insufficient_credit", "ok"]
