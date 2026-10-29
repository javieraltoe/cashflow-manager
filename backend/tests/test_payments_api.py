"""HU04: registrar pagos parciales/totales, anulación con motivo, consultas y auditoría."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Payment
from tests.helpers import set_today

pytestmark = pytest.mark.integration

URL = "/api/v1/payments"
INVOICES = "/api/v1/invoices"
HOY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def _hoy_fijo():
    set_today(HOY)


@pytest.fixture
def client_id(api, operator_h) -> str:
    return api.post("/api/v1/clients", headers=operator_h, json={"name": "ACME SA"}).json()["id"]


def _invoice(api, headers, client_id, **data) -> str:
    payload = {
        "client_id": client_id,
        "invoice_number": "F-0001",
        "issue_date": "2026-10-01",
        "due_date": "2026-10-30",
        "amount": "125000.50",
    } | data
    resp = api.post(INVOICES, headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
def invoice_id(api, operator_h, client_id) -> str:
    return _invoice(api, operator_h, client_id)


def _pay(api, headers, invoice_id, amount="25000.25", **data):
    payload = {"invoice_id": invoice_id, "amount": amount, "method": "transferencia"} | data
    return api.post(URL, headers=headers, json=payload)


def _get_invoice(api, headers, invoice_id) -> dict:
    return api.get(f"{INVOICES}/{invoice_id}", headers=headers).json()


# ---------- Criterios de aceptación, con los ejemplos de las HU ----------


def test_hu04_pago_parcial_exacto_y_no_se_paga_mas_de_lo_adeudado(api, operator_h, client_id):
    """HU04: factura de $1.000, pago de $400 → saldo $600,00 exacto; un pago de $700 se rechaza."""
    inv_id = _invoice(api, operator_h, client_id, invoice_number="HU04", amount="1000.00")
    resp = _pay(api, operator_h, inv_id, "400.00")
    assert resp.status_code == 201
    assert resp.json()["invoice_balance"] == "600.00"
    assert _get_invoice(api, operator_h, inv_id)["balance"] == "600.00"

    resp = _pay(api, operator_h, inv_id, "700.00")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "amount_exceeds_balance"
    assert _get_invoice(api, operator_h, inv_id)["balance"] == "600.00"


def test_hu09_anular_pago_con_motivo_sube_el_saldo_y_queda_auditado(
    api, db, admin, admin_h, operator_h, client_id
):
    """HU09: el admin anula con motivo; el pago no se borra, el saldo vuelve a subir y queda
    registrado quién lo anuló, cuándo y por qué."""
    inv_id = _invoice(api, operator_h, client_id, invoice_number="HU09", amount="1000.00")
    pay_id = _pay(api, operator_h, inv_id, "400.00", method="cheque").json()["id"]

    resp = api.post(f"{URL}/{pay_id}/void", headers=admin_h, json={"reason": "cheque rechazado"})
    assert resp.status_code == 200
    assert resp.json()["invoice_balance"] == "1000.00"
    assert _get_invoice(api, operator_h, inv_id)["balance"] == "1000.00"

    fila = db.get(Payment, uuid.UUID(pay_id))  # no se borró
    db.refresh(fila)
    assert fila.is_void is True
    assert fila.void_reason == "cheque rechazado"  # por qué
    assert fila.voided_at is not None  # cuándo
    ev = db.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == fila.id, AuditEvent.action == "void")
    ).one()
    assert ev.actor_user_id == admin.id  # quién
    assert ev.created_at is not None
    assert ev.details["reason"] == "cheque rechazado"


# ---------- Registro ----------


def test_pago_parcial_actualiza_saldo_y_estado(api, operator, operator_h, invoice_id):
    resp = _pay(api, operator_h, invoice_id, reference="TRF 123")
    assert resp.status_code == 201, resp.text
    pay = resp.json()
    assert pay["amount"] == "25000.25"
    assert pay["method"] == "transferencia"
    assert pay["reference"] == "TRF 123"
    assert pay["payment_date"] == HOY.isoformat()  # por defecto, hoy
    assert pay["invoice_number"] == "F-0001"
    assert pay["client_name"] == "ACME SA"
    assert pay["created_by"] == str(operator.id)
    assert pay["is_void"] is False
    assert pay["invoice_balance"] == "100000.25"
    assert pay["invoice_status"] == "PARCIAL"

    inv = _get_invoice(api, operator_h, invoice_id)
    assert inv["paid_amount"] == "25000.25"
    assert inv["balance"] == "100000.25"
    assert inv["status"] == "PARCIAL"


def test_varios_pagos_hasta_el_total_pagada(api, operator_h, invoice_id):
    assert _pay(api, operator_h, invoice_id, "100000.00").status_code == 201
    resp = _pay(api, operator_h, invoice_id, "25000.50", method="efectivo")
    assert resp.status_code == 201
    assert resp.json()["invoice_balance"] == "0.00"
    assert resp.json()["invoice_status"] == "PAGADA"

    resp = _pay(api, operator_h, invoice_id, "1.00")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invoice_already_paid"


def test_pago_mayor_al_saldo_409(api, operator_h, invoice_id):
    _pay(api, operator_h, invoice_id, "125000.00")
    resp = _pay(api, operator_h, invoice_id, "0.51")
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "amount_exceeds_balance",
        "message": "El pago supera el saldo pendiente (0.50). Para dejar el excedente (0.01) "
        "como saldo a favor, confirmalo con allow_credit.",
        "field": "amount",
    }
    assert _get_invoice(api, operator_h, invoice_id)["balance"] == "0.50"


@pytest.mark.parametrize("amount", ["0", "-1", "10.555", "1234567890123456", "abc"])
def test_importe_invalido_422(api, operator_h, invoice_id, amount):
    resp = _pay(api, operator_h, invoice_id, amount)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "amount"


def test_medio_de_pago_invalido_422(api, operator_h, invoice_id):
    resp = _pay(api, operator_h, invoice_id, method="bitcoin")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "method"


def test_fechas_de_pago(api, operator_h, invoice_id):
    resp = _pay(api, operator_h, invoice_id, payment_date="2026-10-29")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "payment_date"

    # Anticipo: el pago puede ser anterior a la emisión de la factura.
    resp = _pay(api, operator_h, invoice_id, payment_date="2026-09-30")
    assert resp.status_code == 201
    assert resp.json()["payment_date"] == "2026-09-30"

    resp = _pay(api, operator_h, invoice_id, payment_date=HOY.isoformat())
    assert resp.status_code == 201


def test_referencia_vacia_se_guarda_como_null(api, operator_h, invoice_id):
    assert _pay(api, operator_h, invoice_id, reference="   ").json()["reference"] is None


def test_factura_inexistente_404(api, operator_h):
    resp = _pay(api, operator_h, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "invoice_not_found"
    assert resp.json()["error"]["field"] == "invoice_id"


def test_factura_anulada_no_admite_pagos(api, admin_h, operator_h, invoice_id):
    api.patch(f"{INVOICES}/{invoice_id}", headers=admin_h, json={"is_void": True})
    resp = _pay(api, operator_h, invoice_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invoice_void"


def test_cliente_inactivo_igual_puede_pagar(api, operator_h, client_id, invoice_id):
    api.patch(f"/api/v1/clients/{client_id}", headers=operator_h, json={"is_active": False})
    assert _pay(api, operator_h, invoice_id).status_code == 201


def test_pago_parcial_de_factura_vencida_sigue_vencida(api, operator_h, client_id):
    inv_id = _invoice(api, operator_h, client_id, invoice_number="F-V", due_date="2026-10-20")
    resp = _pay(api, operator_h, inv_id, "25000.50")
    assert resp.json()["invoice_status"] == "VENCIDA"
    assert _get_invoice(api, operator_h, inv_id)["days_overdue"] == 8

    resp = _pay(api, operator_h, inv_id, "100000.00")
    assert resp.json()["invoice_status"] == "PAGADA"
    assert _get_invoice(api, operator_h, inv_id)["days_overdue"] == 0


def test_registro_queda_auditado(api, db, operator, operator_h, invoice_id):
    pay_id = _pay(api, operator_h, invoice_id).json()["id"]
    ev = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "payment", AuditEvent.entity_id == uuid.UUID(pay_id)
        )
    ).one()
    assert ev.action == "create"
    assert ev.actor_user_id == operator.id
    assert ev.details["invoice_id"] == invoice_id
    assert ev.details["amount"] == "25000.25"
    assert ev.details["method"] == "transferencia"
    assert ev.details["balance_before"] == "125000.50"
    assert ev.details["balance_after"] == "100000.25"


# ---------- Idempotencia ----------


def _pay_key(api, headers, invoice_id, key, amount="25000.25", **data):
    return _pay(api, headers | {"Idempotency-Key": str(key)}, invoice_id, amount, **data)


def test_reintento_con_la_misma_clave_no_duplica(api, operator_h, invoice_id):
    key = uuid.uuid4()
    first = _pay_key(api, operator_h, invoice_id, key)
    assert first.status_code == 201
    assert "Idempotent-Replayed" not in first.headers

    again = _pay_key(api, operator_h, invoice_id, key)
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    assert _get_invoice(api, operator_h, invoice_id)["paid_amount"] == "25000.25"
    assert api.get(URL, headers=operator_h).json()["total"] == 1


def test_reintento_del_pago_que_salda_la_factura(api, operator_h, invoice_id):
    key = uuid.uuid4()
    assert _pay_key(api, operator_h, invoice_id, key, "125000.50").status_code == 201
    again = _pay_key(api, operator_h, invoice_id, key, "125000.50")
    assert again.status_code == 200  # no es invoice_already_paid
    assert again.json()["invoice_status"] == "PAGADA"


def test_misma_clave_con_otros_datos_409(api, operator_h, invoice_id):
    key = uuid.uuid4()
    _pay_key(api, operator_h, invoice_id, key)
    resp = _pay_key(api, operator_h, invoice_id, key, "1.00")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_key_reused"


def test_claves_distintas_son_pagos_distintos(api, operator_h, invoice_id):
    assert _pay_key(api, operator_h, invoice_id, uuid.uuid4()).status_code == 201
    assert _pay_key(api, operator_h, invoice_id, uuid.uuid4()).status_code == 201
    assert _get_invoice(api, operator_h, invoice_id)["paid_amount"] == "50000.50"


def test_clave_invalida_422(api, operator_h, invoice_id):
    resp = _pay_key(api, operator_h, invoice_id, "no-es-un-uuid")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "idempotency-key"


# ---------- Anulación ----------


def test_operador_no_puede_anular_pago(api, operator_h, invoice_id):
    pay_id = _pay(api, operator_h, invoice_id).json()["id"]
    resp = api.post(f"{URL}/{pay_id}/void", headers=operator_h, json={"reason": "Error de carga"})
    assert resp.status_code == 403


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "  ab  "}])
def test_anular_exige_motivo(api, admin_h, operator_h, invoice_id, body):
    pay_id = _pay(api, operator_h, invoice_id).json()["id"]
    resp = api.post(f"{URL}/{pay_id}/void", headers=admin_h, json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "reason"


def test_admin_anula_pago_y_se_recupera_el_saldo(api, db, admin, admin_h, operator_h, invoice_id):
    pay_id = _pay(api, operator_h, invoice_id, "125000.50").json()["id"]
    assert _get_invoice(api, operator_h, invoice_id)["status"] == "PAGADA"

    resp = api.post(
        f"{URL}/{pay_id}/void", headers=admin_h, json={"reason": "  Cheque rechazado  "}
    )
    assert resp.status_code == 200, resp.text
    pay = resp.json()
    assert pay["is_void"] is True
    assert pay["void_reason"] == "Cheque rechazado"
    assert pay["voided_at"] is not None
    assert pay["invoice_balance"] == "125000.50"
    assert pay["invoice_status"] == "PENDIENTE"

    inv = _get_invoice(api, operator_h, invoice_id)
    assert inv["paid_amount"] == "0.00"
    assert inv["status"] == "PENDIENTE"

    ev = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(pay_id), AuditEvent.action == "void"
        )
    ).one()
    assert ev.actor_user_id == admin.id
    assert ev.details["reason"] == "Cheque rechazado"
    assert ev.details["amount"] == "125000.50"


def test_no_se_anula_dos_veces(api, admin_h, operator_h, invoice_id):
    pay_id = _pay(api, operator_h, invoice_id).json()["id"]
    api.post(f"{URL}/{pay_id}/void", headers=admin_h, json={"reason": "Duplicado"})
    resp = api.post(f"{URL}/{pay_id}/void", headers=admin_h, json={"reason": "Duplicado"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "payment_already_void"


def test_anular_pago_inexistente_404(api, admin_h):
    resp = api.post(f"{URL}/{uuid.uuid4()}/void", headers=admin_h, json={"reason": "No existe"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "payment_not_found"


def test_anulado_el_pago_se_puede_anular_la_factura(api, admin_h, operator_h, invoice_id):
    pay_id = _pay(api, operator_h, invoice_id).json()["id"]
    resp = api.patch(f"{INVOICES}/{invoice_id}", headers=admin_h, json={"is_void": True})
    assert resp.json()["error"]["code"] == "invoice_has_payments"

    api.post(f"{URL}/{pay_id}/void", headers=admin_h, json={"reason": "Factura mal emitida"})
    resp = api.patch(f"{INVOICES}/{invoice_id}", headers=admin_h, json={"is_void": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ANULADA"


def test_importe_de_factura_no_baja_de_lo_cobrado_por_servicio(api, operator_h, invoice_id):
    _pay(api, operator_h, invoice_id, "50000.00")
    resp = api.patch(f"{INVOICES}/{invoice_id}", headers=operator_h, json={"amount": "49999.99"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "amount_below_paid"


# ---------- Consultas ----------


def test_listado_filtros_y_orden(api, admin_h, operator_h, client_id, invoice_id):
    otro = api.post("/api/v1/clients", headers=operator_h, json={"name": "Beta SRL"}).json()["id"]
    inv2 = _invoice(api, operator_h, otro, invoice_number="B-1", amount="1000.00")

    p1 = _pay(api, operator_h, invoice_id, "100.00", payment_date="2026-10-05").json()["id"]
    p2 = _pay(api, operator_h, invoice_id, "200.00", method="cheque").json()["id"]
    p3 = _pay(api, operator_h, inv2, "300.00", payment_date="2026-10-15").json()["id"]
    api.post(f"{URL}/{p1}/void", headers=admin_h, json={"reason": "Error de carga"})

    def ids(**params):
        body = api.get(URL, headers=operator_h, params=params).json()
        return [p["id"] for p in body["items"]], body["total"]

    assert ids() == ([p2, p3], 2)  # por defecto: vigentes, más recientes primero
    assert ids(include_void=True) == ([p2, p3, p1], 3)
    assert ids(invoice_id=invoice_id) == ([p2], 1)
    assert ids(client_id=otro) == ([p3], 1)
    assert ids(method="cheque") == ([p2], 1)
    assert ids(date_from="2026-10-10", date_to="2026-10-20") == ([p3], 1)
    assert ids(sort="amount") == ([p2, p3], 2)
    assert ids(sort="-amount", page_size=1, page=2) == ([p2], 2)

    detalle = api.get(f"{URL}/{p3}", headers=operator_h).json()
    assert detalle["client_name"] == "Beta SRL"
    assert detalle["invoice_balance"] == "700.00"


def test_pago_inexistente_404(api, operator_h):
    assert api.get(f"{URL}/{uuid.uuid4()}", headers=operator_h).status_code == 404


def test_requiere_autenticacion(api):
    assert api.get(URL).status_code == 401
    assert api.post(URL, json={}).status_code == 401
