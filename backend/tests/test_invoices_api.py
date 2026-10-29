"""HU03 / HU05: facturas, saldo, estado calculado, filtros y anulación."""

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Payment
from app.schemas.common import Pagination
from app.services import invoices as invoices_service
from app.services.invoice_rules import InvoiceStatus, compute_status
from app.services.invoices import InvoiceFilters
from tests.helpers import set_today

pytestmark = pytest.mark.integration

URL = "/api/v1/invoices"
HOY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def _hoy_fijo():
    set_today(HOY)


@pytest.fixture
def client_id(api, operator_h) -> str:
    return api.post("/api/v1/clients", headers=operator_h, json={"name": "ACME SA"}).json()["id"]


def _invoice(api, headers, client_id, **data):
    payload = {
        "client_id": client_id,
        "invoice_number": "F-0001",
        "issue_date": "2026-10-01",
        "due_date": "2026-10-30",
        "amount": "125000.50",
        "description": "Servicio mensual",
    } | data
    return api.post(URL, headers=headers, json=payload)


def _pay(db, invoice_id, amount, user, void=False, when=HOY):
    """Inserta un pago directo en la base (el servicio de pagos llega en el Sprint 2)."""
    db.add(
        Payment(
            invoice_id=uuid.UUID(invoice_id),
            payment_date=when,
            amount=Decimal(amount),
            method="transferencia",
            created_by=user.id,
            is_void=void,
        )
    )
    db.commit()


# ---------- HU03: alta y saldo ----------


def test_crear_factura_muestra_saldo(api, operator_h, client_id):
    resp = _invoice(api, operator_h, client_id)
    assert resp.status_code == 201
    inv = resp.json()
    # Montos como string: sin pérdida de precisión
    assert inv["amount"] == "125000.50"
    assert inv["paid_amount"] == "0.00"
    assert inv["balance"] == "125000.50"
    assert inv["status"] == "PENDIENTE"
    assert inv["days_overdue"] == 0
    assert inv["currency"] == "ARS"
    assert inv["client_name"] == "ACME SA"


def test_numero_duplicado_mismo_cliente_409(api, operator_h, client_id):
    _invoice(api, operator_h, client_id)
    resp = _invoice(api, operator_h, client_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "duplicate_invoice_number"
    assert resp.json()["error"]["field"] == "invoice_number"


def test_mismo_numero_en_otro_cliente_se_permite(api, operator_h, client_id):
    otro = api.post("/api/v1/clients", headers=operator_h, json={"name": "Beta SRL"}).json()["id"]
    assert _invoice(api, operator_h, client_id).status_code == 201
    assert _invoice(api, operator_h, otro).status_code == 201


@pytest.mark.parametrize("amount", ["0", "-10", "10.555", "1234567890123456"])
def test_importe_invalido_422(api, operator_h, client_id, amount):
    resp = _invoice(api, operator_h, client_id, amount=amount)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "amount"


def test_moneda_distinta_de_ars_rechazada(api, operator_h, client_id):
    resp = _invoice(api, operator_h, client_id, currency="USD")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "currency"


def test_vencimiento_anterior_a_emision_422(api, operator_h, client_id):
    resp = _invoice(api, operator_h, client_id, issue_date="2026-10-10", due_date="2026-10-01")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "due_date"


def test_cliente_inexistente_o_inactivo(api, operator_h, client_id):
    resp = _invoice(api, operator_h, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["error"]["field"] == "client_id"

    api.patch(f"/api/v1/clients/{client_id}", headers=operator_h, json={"is_active": False})
    resp = _invoice(api, operator_h, client_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "client_inactive"


# ---------- Saldo y estados con pagos (spec §5) ----------


def test_pago_parcial_baja_el_saldo_exacto(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id).json()["id"]
    _pay(db, inv_id, "25000.25", operator)
    inv = api.get(f"{URL}/{inv_id}", headers=operator_h).json()
    assert inv["paid_amount"] == "25000.25"
    assert inv["balance"] == "100000.25"
    assert inv["status"] == "PARCIAL"


def test_pagos_anulados_no_cuentan(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id).json()["id"]
    _pay(db, inv_id, "1000.00", operator, void=True)
    assert api.get(f"{URL}/{inv_id}", headers=operator_h).json()["balance"] == "125000.50"


def test_pago_total_pagada(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id, amount="1000.00").json()["id"]
    _pay(db, inv_id, "400.00", operator)
    _pay(db, inv_id, "600.00", operator)
    inv = api.get(f"{URL}/{inv_id}", headers=operator_h).json()
    assert inv["balance"] == "0.00"
    assert inv["status"] == "PAGADA"


def test_hu05_vence_sola_sin_intervencion(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id, due_date="2026-10-30").json()["id"]
    assert api.get(f"{URL}/{inv_id}", headers=operator_h).json()["status"] == "PENDIENTE"

    set_today(date(2026, 11, 9))  # pasan los días, nadie toca la factura
    inv = api.get(f"{URL}/{inv_id}", headers=operator_h).json()
    assert inv["status"] == "VENCIDA"
    assert inv["days_overdue"] == 10


def test_parcial_vencida_es_vencida_y_conserva_saldo(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id, amount="1000.00", due_date="2026-10-20").json()[
        "id"
    ]
    _pay(db, inv_id, "300.00", operator)
    inv = api.get(f"{URL}/{inv_id}", headers=operator_h).json()
    assert inv["status"] == "VENCIDA"
    assert inv["balance"] == "700.00"
    assert inv["days_overdue"] == 8


def test_estado_sql_coincide_con_regla_python(db, admin, api, admin_h):
    """El filtro por estado (SQL) y el estado mostrado (Python) usan el mismo criterio."""
    cid = api.post("/api/v1/clients", headers=admin_h, json={"name": "Matriz"}).json()["id"]
    dues = [HOY - timedelta(days=5), HOY, HOY + timedelta(days=5)]
    paids = ["0", "300.00", "1000.00"]
    for n, (due, paid) in enumerate(itertools.product(dues, paids)):
        inv_id = _invoice(
            api,
            admin_h,
            cid,
            invoice_number=f"M-{n}",
            issue_date="2026-01-01",
            due_date=due.isoformat(),
            amount="1000.00",
        ).json()["id"]
        if paid != "0":
            _pay(db, inv_id, paid, admin)

    total = 0
    for st in InvoiceStatus:
        items, count = invoices_service.list_invoices(
            db, InvoiceFilters(status=st), Pagination(page_size=100), HOY
        )
        total += count if st != InvoiceStatus.ANULADA else 0
        for it in items:
            assert it.status == st
            assert compute_status(it.amount, it.paid_amount, it.due_date, HOY) == st
    assert total == 9


# ---------- Filtros ----------


def test_filtros_por_cliente_estado_y_vencimiento(api, db, operator, operator_h, client_id):
    otro = api.post("/api/v1/clients", headers=operator_h, json={"name": "Beta"}).json()["id"]
    _invoice(api, operator_h, client_id, invoice_number="A1", due_date="2026-10-15")
    _invoice(api, operator_h, client_id, invoice_number="A2", due_date="2026-11-15")
    _invoice(api, operator_h, otro, invoice_number="B1", due_date="2026-11-20")

    def ids(**params):
        r = api.get(URL, headers=operator_h, params=params).json()
        return sorted(i["invoice_number"] for i in r["items"])

    assert ids(client_id=client_id) == ["A1", "A2"]
    assert ids(status="VENCIDA") == ["A1"]
    assert ids(status="PENDIENTE") == ["A2", "B1"]
    assert ids(due_from="2026-11-01", due_to="2026-11-16") == ["A2"]
    assert ids(q="b") == ["B1"]
    assert ids(client_id=client_id, status="PENDIENTE") == ["A2"]


def test_orden_por_vencimiento_desc(api, operator_h, client_id):
    for n, due in (("X1", "2026-11-01"), ("X2", "2026-12-01"), ("X3", "2026-10-29")):
        _invoice(api, operator_h, client_id, invoice_number=n, due_date=due)
    r = api.get(URL, headers=operator_h, params={"sort": "-due_date"}).json()
    assert [i["invoice_number"] for i in r["items"]] == ["X2", "X1", "X3"]


# ---------- Edición y anulación ----------


def test_editar_factura_queda_auditado(api, db, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id).json()["id"]
    resp = api.patch(
        f"{URL}/{inv_id}", headers=operator_h, json={"amount": "130000.00", "description": None}
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == "130000.00"
    assert resp.json()["description"] is None

    ev = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(inv_id), AuditEvent.action == "update"
        )
    )
    assert ev.details["amount"] == {"from": "125000.50", "to": "130000.00"}


def test_importe_no_puede_quedar_debajo_de_lo_cobrado(api, db, operator, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id, amount="1000.00").json()["id"]
    _pay(db, inv_id, "600.00", operator)
    resp = api.patch(f"{URL}/{inv_id}", headers=operator_h, json={"amount": "500.00"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "amount_below_paid"


def test_editar_vencimiento_antes_de_emision_422(api, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id).json()["id"]
    resp = api.patch(f"{URL}/{inv_id}", headers=operator_h, json={"due_date": "2026-09-01"})
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "due_date"


def test_renumerar_a_numero_existente_409(api, operator_h, client_id):
    _invoice(api, operator_h, client_id, invoice_number="F-1")
    inv_id = _invoice(api, operator_h, client_id, invoice_number="F-2").json()["id"]
    resp = api.patch(f"{URL}/{inv_id}", headers=operator_h, json={"invoice_number": "F-1"})
    assert resp.status_code == 409


def test_operador_no_puede_anular(api, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id).json()["id"]
    resp = api.patch(f"{URL}/{inv_id}", headers=operator_h, json={"is_void": True})
    assert resp.status_code == 403


def test_no_se_anula_con_pagos_vigentes(api, db, admin, admin_h, client_id):
    inv_id = _invoice(api, admin_h, client_id).json()["id"]
    _pay(db, inv_id, "10.00", admin)
    resp = api.patch(f"{URL}/{inv_id}", headers=admin_h, json={"is_void": True})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invoice_has_payments"


def test_anulacion_por_admin(api, admin_h, client_id):
    inv_id = _invoice(api, admin_h, client_id).json()["id"]
    resp = api.patch(f"{URL}/{inv_id}", headers=admin_h, json={"is_void": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ANULADA"

    assert api.get(URL, headers=admin_h).json()["total"] == 0  # excluida por defecto
    assert api.get(URL, headers=admin_h, params={"include_void": True}).json()["total"] == 1
    assert api.get(URL, headers=admin_h, params={"status": "ANULADA"}).json()["total"] == 1

    resp = api.patch(f"{URL}/{inv_id}", headers=admin_h, json={"description": "x"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invoice_void"
    # No se puede "des-anular"
    assert api.patch(f"{URL}/{inv_id}", headers=admin_h, json={"is_void": False}).status_code == 422


def test_requiere_autenticacion(api):
    assert api.get(URL).status_code == 401
    assert api.post(URL, json={}).status_code == 401
