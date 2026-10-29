"""Saldo a favor del cliente (ADR-0003 #6): excedente confirmado, cobro a cuenta,
imputación manual a facturas y anulación bloqueada si el crédito ya se usó."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditEvent
from tests.helpers import set_today

pytestmark = pytest.mark.integration

PAYMENTS = "/api/v1/payments"
CREDITS = "/api/v1/credits"
INVOICES = "/api/v1/invoices"
HOY = date(2026, 10, 28)


@pytest.fixture(autouse=True)
def _hoy_fijo():
    set_today(HOY)


@pytest.fixture
def client_id(api, operator_h) -> str:
    return api.post("/api/v1/clients", headers=operator_h, json={"name": "ACME SA"}).json()["id"]


def _invoice(api, headers, client_id, number="F-0001", amount="125000.00") -> str:
    resp = api.post(
        INVOICES,
        headers=headers,
        json={
            "client_id": client_id,
            "invoice_number": number,
            "issue_date": "2026-10-01",
            "due_date": "2026-10-30",
            "amount": amount,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture
def invoice_id(api, operator_h, client_id) -> str:
    return _invoice(api, operator_h, client_id)


def _pay(api, headers, invoice_id, amount, **data):
    payload = {"invoice_id": invoice_id, "amount": amount, "method": "transferencia"} | data
    return api.post(PAYMENTS, headers=headers, json=payload)


def _on_account(api, headers, client_id, amount="5000.00", **data):
    payload = {"client_id": client_id, "amount": amount, "method": "efectivo"} | data
    return api.post(CREDITS, headers=headers, json=payload)


def _apply(api, headers, invoice_id, amount, **extra):
    return api.post(
        f"{CREDITS}/apply",
        headers=headers,
        json={"invoice_id": invoice_id, "amount": amount},
        **extra,
    )


def _balance(api, headers, client_id) -> dict:
    return api.get(f"/api/v1/clients/{client_id}/credit", headers=headers).json()


def _void(api, headers, url, reason="Error de carga"):
    return api.post(f"{url}/void", headers=headers, json={"reason": reason})


# ---------- Excedente de un pago ----------


def test_sobrepago_sin_confirmar_se_rechaza(api, operator_h, client_id, invoice_id):
    resp = _pay(api, operator_h, invoice_id, "125100.00")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "amount_exceeds_balance"
    assert "(100.00)" in resp.json()["error"]["message"]
    assert _balance(api, operator_h, client_id)["available"] == "0.00"


def test_sobrepago_confirmado_deja_saldo_a_favor(
    api, db, operator, operator_h, client_id, invoice_id
):
    resp = _pay(api, operator_h, invoice_id, "125100.00", allow_credit=True, reference="TRF 9")
    assert resp.status_code == 201, resp.text
    pay = resp.json()
    assert pay["amount"] == "125000.00"  # imputado a la factura
    assert pay["credit_amount"] == "100.00"  # excedente
    assert pay["invoice_status"] == "PAGADA"
    assert pay["invoice_balance"] == "0.00"

    assert _balance(api, operator_h, client_id) == {
        "client_id": client_id,
        "credited": "100.00",
        "applied": "0.00",
        "available": "100.00",
    }
    credit = api.get(CREDITS, headers=operator_h, params={"client_id": client_id}).json()["items"]
    assert len(credit) == 1
    assert credit[0]["origin"] == "excedente"
    assert credit[0]["payment_id"] == pay["id"]
    assert credit[0]["reference"] == "TRF 9"
    assert credit[0]["method"] == "transferencia"

    ev = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(pay["id"]))).one()
    assert ev.details["received"] == "125100.00"
    assert ev.details["amount"] == "125000.00"
    assert ev.details["credit_amount"] == "100.00"


def test_allow_credit_sin_excedente_no_crea_credito(api, operator_h, client_id, invoice_id):
    resp = _pay(api, operator_h, invoice_id, "1000.00", allow_credit=True)
    assert resp.json()["credit_amount"] == "0.00"
    assert _balance(api, operator_h, client_id)["credited"] == "0.00"


def test_factura_ya_pagada_no_admite_sobrepago(api, operator_h, invoice_id):
    _pay(api, operator_h, invoice_id, "125000.00")
    resp = _pay(api, operator_h, invoice_id, "10.00", allow_credit=True)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "invoice_already_paid"


# ---------- Cobro a cuenta ----------


def test_cobro_a_cuenta(api, db, operator, operator_h, client_id):
    resp = _on_account(api, operator_h, client_id, "5000.00", reference="Anticipo obra")
    assert resp.status_code == 201, resp.text
    credit = resp.json()
    assert credit["origin"] == "a_cuenta"
    assert credit["payment_id"] is None
    assert credit["credit_date"] == HOY.isoformat()
    assert credit["client_name"] == "ACME SA"
    assert credit["client_available"] == "5000.00"
    assert credit["created_by"] == str(operator.id)

    ev = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(credit["id"]))).one()
    assert ev.entity_type == "credit"
    assert ev.details["origin"] == "a_cuenta"


def test_cobro_a_cuenta_validaciones(api, operator_h, client_id):
    assert _on_account(api, operator_h, client_id, "0").status_code == 422
    assert _on_account(api, operator_h, client_id, method="bitcoin").status_code == 422
    resp = _on_account(api, operator_h, client_id, payment_date="2026-10-29")
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "payment_date"
    resp = _on_account(api, operator_h, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["error"]["field"] == "client_id"

    api.patch(f"/api/v1/clients/{client_id}", headers=operator_h, json={"is_active": False})
    resp = _on_account(api, operator_h, client_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "client_inactive"


def test_cobro_a_cuenta_idempotente(api, operator_h, client_id):
    h = operator_h | {"Idempotency-Key": str(uuid.uuid4())}
    first = _on_account(api, h, client_id)
    again = _on_account(api, h, client_id)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert _balance(api, operator_h, client_id)["available"] == "5000.00"
    assert _on_account(api, h, client_id, "1.00").json()["error"]["code"] == (
        "idempotency_key_reused"
    )


# ---------- Imputación manual ----------


def test_imputar_saldo_a_favor_a_otra_factura(api, db, operator_h, client_id, invoice_id):
    _on_account(api, operator_h, client_id, "5000.00")
    resp = _apply(api, operator_h, invoice_id, "3000.00")
    assert resp.status_code == 201, resp.text
    pay = resp.json()
    assert pay["method"] == "saldo_a_favor"
    assert pay["amount"] == "3000.00"
    assert pay["payment_date"] == HOY.isoformat()
    assert pay["invoice_balance"] == "122000.00"
    assert pay["invoice_status"] == "PARCIAL"
    assert _balance(api, operator_h, client_id) == {
        "client_id": client_id,
        "credited": "5000.00",
        "applied": "3000.00",
        "available": "2000.00",
    }
    resp = api.get(PAYMENTS, headers=operator_h, params={"method": "saldo_a_favor"})
    assert resp.json()["total"] == 1


def test_imputar_mas_que_el_disponible_409(api, operator_h, client_id, invoice_id):
    _on_account(api, operator_h, client_id, "5000.00")
    resp = _apply(api, operator_h, invoice_id, "5000.01")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "insufficient_credit"
    assert "(disponible: 5000.00)" in resp.json()["error"]["message"]


def test_imputar_mas_que_el_saldo_de_la_factura_409(api, operator_h, client_id):
    chica = _invoice(api, operator_h, client_id, "F-CHICA", "100.00")
    _on_account(api, operator_h, client_id, "5000.00")
    resp = _apply(api, operator_h, chica, "100.01")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "amount_exceeds_balance"


def test_credito_de_un_cliente_no_paga_facturas_de_otro(api, operator_h, client_id):
    otro = api.post("/api/v1/clients", headers=operator_h, json={"name": "Beta SRL"}).json()["id"]
    factura_otro = _invoice(api, operator_h, otro, "B-1", "1000.00")
    _on_account(api, operator_h, client_id, "5000.00")
    resp = _apply(api, operator_h, factura_otro, "100.00")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "insufficient_credit"


def test_imputacion_idempotente(api, operator_h, client_id, invoice_id):
    _on_account(api, operator_h, client_id, "5000.00")
    h = operator_h | {"Idempotency-Key": str(uuid.uuid4())}
    first = _apply(api, h, invoice_id, "1000.00")
    again = _apply(api, h, invoice_id, "1000.00")
    assert (first.status_code, again.status_code) == (201, 200)
    assert _balance(api, operator_h, client_id)["available"] == "4000.00"


# ---------- Anulación ----------


def test_anular_imputacion_devuelve_el_credito(api, admin_h, operator_h, client_id, invoice_id):
    _on_account(api, operator_h, client_id, "5000.00")
    pay_id = _apply(api, operator_h, invoice_id, "3000.00").json()["id"]
    resp = _void(api, admin_h, f"{PAYMENTS}/{pay_id}")
    assert resp.status_code == 200
    assert resp.json()["invoice_balance"] == "125000.00"
    assert _balance(api, operator_h, client_id)["available"] == "5000.00"


def test_anular_pago_con_excedente_sin_usar_anula_el_credito(
    api, admin_h, operator_h, client_id, invoice_id
):
    pay_id = _pay(api, operator_h, invoice_id, "125100.00", allow_credit=True).json()["id"]
    resp = _void(api, admin_h, f"{PAYMENTS}/{pay_id}", "Transferencia rechazada")
    assert resp.status_code == 200
    assert resp.json()["invoice_status"] == "PENDIENTE"
    assert _balance(api, operator_h, client_id)["available"] == "0.00"
    credit = api.get(CREDITS, headers=operator_h, params={"include_void": True}).json()["items"][0]
    assert credit["is_void"] is True
    assert credit["void_reason"] == "Transferencia rechazada"


def test_anular_pago_con_excedente_ya_usado_se_bloquea(
    api, admin_h, operator_h, client_id, invoice_id
):
    otra = _invoice(api, operator_h, client_id, "F-0002", "1000.00")
    pay_id = _pay(api, operator_h, invoice_id, "125100.00", allow_credit=True).json()["id"]
    apl_id = _apply(api, operator_h, otra, "60.00").json()["id"]

    resp = _void(api, admin_h, f"{PAYMENTS}/{pay_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "credit_in_use"
    assert "(disponible: 40.00)" in resp.json()["error"]["message"]
    assert api.get(f"{PAYMENTS}/{pay_id}", headers=operator_h).json()["is_void"] is False

    # Anulando primero la imputación, ya se puede anular el pago original.
    assert _void(api, admin_h, f"{PAYMENTS}/{apl_id}").status_code == 200
    assert _void(api, admin_h, f"{PAYMENTS}/{pay_id}").status_code == 200
    assert _balance(api, operator_h, client_id)["available"] == "0.00"


def test_anular_cobro_a_cuenta(api, db, admin, admin_h, operator_h, client_id, invoice_id):
    credit_id = _on_account(api, operator_h, client_id, "5000.00").json()["id"]
    assert _void(api, operator_h, f"{CREDITS}/{credit_id}").status_code == 403

    apl_id = _apply(api, operator_h, invoice_id, "1000.00").json()["id"]
    resp = _void(api, admin_h, f"{CREDITS}/{credit_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "credit_in_use"

    _void(api, admin_h, f"{PAYMENTS}/{apl_id}")
    resp = _void(api, admin_h, f"{CREDITS}/{credit_id}", "Anticipo devuelto")
    assert resp.status_code == 200
    assert resp.json()["is_void"] is True
    assert resp.json()["client_available"] == "0.00"
    assert _void(api, admin_h, f"{CREDITS}/{credit_id}").json()["error"]["code"] == (
        "credit_already_void"
    )
    ev = db.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_id == uuid.UUID(credit_id), AuditEvent.action == "void"
        )
    ).one()
    assert ev.actor_user_id == admin.id
    assert ev.details["reason"] == "Anticipo devuelto"


def test_credito_de_excedente_se_anula_desde_el_pago(api, admin_h, operator_h, invoice_id):
    _pay(api, operator_h, invoice_id, "125100.00", allow_credit=True)
    credit_id = api.get(CREDITS, headers=operator_h).json()["items"][0]["id"]
    resp = _void(api, admin_h, f"{CREDITS}/{credit_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "credit_from_payment"


# ---------- Consultas ----------


def test_consultas_404_y_autenticacion(api, operator_h):
    assert api.get(f"{CREDITS}/{uuid.uuid4()}", headers=operator_h).status_code == 404
    assert api.get(f"/api/v1/clients/{uuid.uuid4()}/credit", headers=operator_h).status_code == 404
    assert api.get(CREDITS).status_code == 401
    assert api.post(f"{CREDITS}/apply", json={}).status_code == 401
