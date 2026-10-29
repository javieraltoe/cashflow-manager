"""Dataset de demostración reconciliado (HU06).

Todas las fechas son RELATIVAS a "hoy" (días antes/después, o el día 1 de un mes
anterior), así los indicadores esperados (EXPECTED) son siempre los mismos, sin importar
el día en que se cargue. La tabla de casos y las consultas SQL para verificarlos a mano
están en docs/runbook/dataset-demo.md.

Uso:  python -m app.cli seed-demo            (base sin clientes)
      python -m app.cli seed-demo --reset    (borra los datos de negocio; nunca en producción)
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Client, ClientCredit, ImportBatch, Invoice, Payment, User

D = Decimal


def month_start(today: date, months_ago: int) -> date:
    y, m = today.year, today.month - months_ago
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


# (clave, nombre, CUIT, activo)
CLIENTS = [
    ("C1", "Almacén Don Pepe", "20-12345678-3", True),
    ("C2", "Constructora Andina SA", "30-71000001-1", True),
    ("C3", "Distribuidora Norte SRL", "30-71000002-9", True),
    ("C4", "Estudio Contable Ríos", "27-23456789-4", True),
    ("C5", "Farmacia Central", "30-71000003-7", True),
    ("C6", "Gráfica del Sur", "30-71000004-5", False),  # inactivo, con deuda vieja
    ("C7", "Hotel Las Lomas", "30-71000005-3", True),  # al día, con saldo a favor
]


@dataclass(frozen=True)
class Inv:
    key: str
    client: str
    number: str
    amount: str
    issue: int  # días respecto de hoy (negativo = pasado)
    due: int
    void: bool = False


# Facturas "de stock": definen saldo por cobrar, vencido, aging y próximos vencimientos.
INVOICES = [
    Inv("A", "C1", "F-1001", "100000.00", -40, -10),  # vencida 10 d, pago parcial
    Inv("B", "C2", "F-2001", "250000.00", -75, -45),  # vencida 45 d
    Inv("C", "C2", "F-2002", "80000.00", -105, -75),  # vencida 75 d, pago parcial
    Inv("D", "C3", "F-3001", "150000.00", -150, -120),  # vencida 120 d
    Inv("E", "C6", "F-6001", "45000.00", -230, -200),  # vencida 200 d, cliente inactivo
    Inv("F", "C4", "F-4001", "60000.00", -27, 3),  # vence en 3 d
    Inv("G", "C5", "F-5001", "90000.00", -24, 6),  # vence en 6 d, pago parcial
    Inv("H", "C1", "F-1002", "120000.00", -10, 20),  # vence en 20 d, imputación de crédito
    Inv("I", "C3", "F-3002", "30000.00", -30, 0),  # vence HOY: todavía no vencida
    Inv("J", "C4", "F-4002", "70000.00", -20, 10, void=True),  # anulada: no cuenta
    Inv("K", "C5", "F-5002", "50000.00", -35, -5),  # vencida 5 d, su pago se anuló
    Inv("L", "C7", "F-7001", "200000.00", -45, -15),  # pagada con excedente
]

# Facturas históricas pagadas el día 1 de cada uno de los 5 meses anteriores.
HISTORY = {1: "300000.00", 2: "220000.00", 3: "180000.00", 4: "260000.00", 5: "150000.00"}

ON_ACCOUNT = ("C1", "15000.00")  # cobro a cuenta (efectivo, hoy)
APPLIED = ("H", "5000.00")  # imputación de saldo a favor de C1 en H (hoy)

# Indicadores esperados (siempre iguales). Período = mes en curso para "cobrado".
EXPECTED = {
    "total_receivable": D("880000.00"),
    "overdue_balance": D("625000.00"),
    "overdue_pct": D("71.02"),
    "overdue_count": 6,
    "due_soon_balance": D("140000.00"),
    "due_soon_count": 3,
    "credit_available": D("20000.00"),
    "collected_current_month": D("315000.00"),
    "collected_payments_current_month": D("290000.00"),
    "collected_credits_current_month": D("25000.00"),
    # meses atrás -> cobrado en ese mes
    "monthly": {
        0: D("315000.00"),
        1: D("300000.00"),
        2: D("220000.00"),
        3: D("180000.00"),
        4: D("260000.00"),
        5: D("150000.00"),
    },  # fmt: skip
    "aging": {
        "1-30": (D("120000.00"), 2),
        "31-60": (D("250000.00"), 1),
        "61-90": (D("60000.00"), 1),
        "91+": (D("195000.00"), 2),
    },
    "top_debtors": [
        ("Constructora Andina SA", D("310000.00"), D("310000.00")),
        ("Almacén Don Pepe", D("185000.00"), D("70000.00")),
        ("Distribuidora Norte SRL", D("180000.00"), D("150000.00")),
        ("Farmacia Central", D("100000.00"), D("50000.00")),
        ("Estudio Contable Ríos", D("60000.00"), D("0.00")),
        ("Gráfica del Sur", D("45000.00"), D("45000.00")),
    ],
    "upcoming_7": ["F-3002", "F-4001", "F-5001"],
}


class SeedError(Exception):
    pass


def reset_business_data(db: Session) -> None:
    """Borra clientes, facturas, pagos, créditos y su auditoría. Conserva los usuarios."""
    db.execute(delete(ClientCredit))
    db.execute(delete(Payment))
    db.execute(delete(Invoice))
    db.execute(delete(ImportBatch))
    db.execute(delete(AuditEvent).where(AuditEvent.entity_type != "user"))
    db.execute(delete(Client))
    db.flush()


def seed_demo(db: Session, today: date, actor: User, reset: bool = False) -> dict:
    if reset:
        reset_business_data(db)
    elif db.scalar(select(func.count()).select_from(Client)):
        raise SeedError("La base ya tiene clientes. Usá --reset para reemplazarlos (borra datos).")

    clients: dict[str, Client] = {}
    for key, name, tax_id, active in CLIENTS:
        clients[key] = Client(id=uuid.uuid4(), name=name, tax_id=tax_id, is_active=active)
    db.add_all(clients.values())
    db.flush()

    def add_invoice(client: str, number: str, amount: str, issue: date, due: date, void=False):
        inv = Invoice(
            id=uuid.uuid4(),
            client_id=clients[client].id,
            invoice_number=number,
            issue_date=issue,
            due_date=due,
            amount=D(amount),
            description="Dato de demostración",
            is_void=void,
            created_by=actor.id,
        )
        db.add(inv)
        return inv

    def add_payment(inv: Invoice, amount: str, when: date, method="transferencia", **extra):
        pay = Payment(
            id=uuid.uuid4(),
            invoice_id=inv.id,
            payment_date=when,
            amount=D(amount),
            method=method,
            created_by=actor.id,
            **extra,
        )
        db.add(pay)
        return pay

    inv = {
        i.key: add_invoice(
            i.client,
            i.number,
            i.amount,
            today + timedelta(days=i.issue),
            today + timedelta(days=i.due),
            i.void,
        )
        for i in INVOICES
    }
    db.flush()

    add_payment(inv["A"], "30000.00", today, reference="TRF 0001")
    add_payment(inv["C"], "20000.00", today, method="cheque", reference="CH 1234")
    add_payment(inv["G"], "40000.00", today, method="efectivo")
    add_payment(
        inv["K"],
        "50000.00",
        today,
        method="cheque",
        is_void=True,
        void_reason="Cheque rechazado",
        voided_at=func.now(),
    )
    excess_from = add_payment(inv["L"], "200000.00", today, reference="TRF 0002")
    db.flush()
    db.add(
        ClientCredit(
            client_id=clients["C7"].id,
            payment_id=excess_from.id,
            credit_date=today,
            amount=D("10000.00"),
            method="transferencia",
            reference="TRF 0002",
            created_by=actor.id,
        )
    )
    client_key, amount = ON_ACCOUNT
    db.add(
        ClientCredit(
            client_id=clients[client_key].id,
            credit_date=today,
            amount=D(amount),
            method="efectivo",
            reference="Anticipo",
            created_by=actor.id,
        )
    )
    inv_key, amount = APPLIED
    add_payment(inv[inv_key], amount, today, method="saldo_a_favor")

    for months_ago, amount in HISTORY.items():
        paid_on = month_start(today, months_ago)
        hist = add_invoice(
            "C7",
            f"H-{months_ago:02d}",
            amount,
            paid_on - timedelta(days=30),
            paid_on - timedelta(days=1),
        )
        db.flush()
        add_payment(hist, amount, paid_on)

    db.commit()
    return {
        "clients": len(CLIENTS),
        "invoices": len(INVOICES) + len(HISTORY),
        "today": today.isoformat(),
    }


def first_admin(db: Session) -> User:
    user = db.scalar(
        select(User)
        .where(User.role == "admin", User.is_active.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )
    if user is None:
        raise SeedError("No hay administradores: creá uno con 'create-admin' primero.")
    return user
