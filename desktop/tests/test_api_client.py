"""ApiClient del escritorio contra la API real (base de test, sin servidor)."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from desktop.app.core.summary import load_home_summary
from desktop.app.services.api import ApiClient, ApiError, SessionExpired, new_idempotency_key
from tests.helpers import TEST_PASSWORD, set_today

pytestmark = pytest.mark.integration

HOY = date(2026, 10, 28)
D = Decimal


@pytest.fixture(autouse=True)
def _hoy():
    set_today(HOY)


def _cliente_y_factura(api: ApiClient, amount="1000.00", due="2026-11-02", number="F-1"):
    c = api.create_client({"name": f"Cliente {number}"})
    inv = api.create_invoice(
        {
            "client_id": c["id"],
            "invoice_number": number,
            "issue_date": date(2026, 10, 1),
            "due_date": date.fromisoformat(due),
            "amount": D(amount),
        }
    )
    return c, inv


# ---------- Sesión ----------


def test_login_carga_el_usuario(client_api, admin):
    user = client_api.login("  ADMIN@demo.com.ar ", TEST_PASSWORD)
    assert user["email"] == "admin@demo.com.ar"
    assert client_api.is_authenticated
    assert client_api.is_admin


def test_login_invalido_mensaje_en_espanol(client_api, admin):
    with pytest.raises(ApiError) as exc:
        client_api.login("admin@demo.com.ar", "incorrecta")
    assert exc.value.status == 401
    assert exc.value.code == "invalid_credentials"
    assert exc.value.message == "Email o contraseña incorrectos"
    assert not client_api.is_authenticated


def test_operador_no_es_admin(operator_api):
    assert not operator_api.is_admin
    with pytest.raises(ApiError) as exc:
        operator_api.list_users()
    assert exc.value.status == 403


def test_access_vencido_se_renueva_solo(admin_api):
    admin_api._access = "token-vencido-o-invalido"
    old_refresh = admin_api._refresh
    assert admin_api.me()["email"] == "admin@demo.com.ar"  # reintentó tras renovar
    assert admin_api._refresh != old_refresh  # el refresh rotó


def test_sesion_expirada_si_el_refresh_ya_no_sirve(admin_api):
    admin_api._access = "token-invalido"
    admin_api._refresh = "refresh-invalido-de-mas-de-20-caracteres"
    with pytest.raises(SessionExpired):
        admin_api.me()
    assert not admin_api.is_authenticated


def test_sin_sesion_no_llama_a_la_api(client_api):
    with pytest.raises(SessionExpired):
        client_api.list_clients()


def test_logout_revoca_el_refresh(admin_api, api):
    refresh = admin_api._refresh
    admin_api.logout()
    assert not admin_api.is_authenticated
    resp = api.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


def test_cambio_de_password(admin_api, client_api, admin):
    admin_api.change_password(TEST_PASSWORD, "otra-clave-segura-1")
    assert client_api.login(admin.email, "otra-clave-segura-1")["role"] == "admin"


# ---------- Errores de red ----------


def _api_con_transporte(handler) -> ApiClient:
    c = ApiClient("http://srv/api/v1", http=httpx.Client(transport=httpx.MockTransport(handler)))
    c._access, c._refresh = "a", "r" * 30
    return c


def test_servidor_caido_da_error_claro():
    def handler(request):
        raise httpx.ConnectError("conexión rechazada")

    with pytest.raises(ApiError) as exc:
        _api_con_transporte(handler).list_clients()
    assert exc.value.code == "network_error"
    assert "No se pudo conectar" in exc.value.message


def test_timeout_da_error_claro():
    def handler(request):
        raise httpx.ReadTimeout("lento")

    with pytest.raises(ApiError) as exc:
        _api_con_transporte(handler).list_clients()
    assert exc.value.code == "timeout"


def test_respuesta_no_json_da_error_generico():
    with pytest.raises(ApiError) as exc:
        _api_con_transporte(lambda r: httpx.Response(502, text="Bad gateway")).list_clients()
    assert exc.value.status == 502
    assert exc.value.code == "http_error"


# ---------- Clientes y facturas ----------


def test_errores_de_validacion_traen_el_campo(admin_api):
    admin_api.create_client({"name": "ACME SA"})
    with pytest.raises(ApiError) as exc:
        admin_api.create_client({"name": "acme sa"})
    assert (exc.value.status, exc.value.field) == (409, "name")


def test_all_clients_recorre_todas_las_paginas(admin_api):
    for n in range(105):
        admin_api.create_client({"name": f"Cliente {n:03d}"})
    todos = admin_api.all_clients()
    assert len(todos) == 105
    assert todos[0]["name"] == "Cliente 000"


def test_montos_viajan_como_string_exacto(admin_api):
    _, inv = _cliente_y_factura(admin_api, amount="125000.50")
    assert inv["amount"] == "125000.50"
    assert inv["balance"] == "125000.50"


def test_filtros_de_facturas(admin_api):
    c, _ = _cliente_y_factura(admin_api, due="2026-10-20", number="V-1")  # vencida
    admin_api.create_invoice(
        {
            "client_id": c["id"],
            "invoice_number": "P-1",
            "issue_date": date(2026, 10, 1),
            "due_date": date(2026, 11, 30),
            "amount": D("10"),
        }
    )
    vencidas = admin_api.list_invoices(status="VENCIDA", client_id=c["id"])
    assert [i["invoice_number"] for i in vencidas["items"]] == ["V-1"]
    assert admin_api.list_invoices(q=None, status=None)["total"] == 2  # None no se envía


# ---------- Pagos (HU04 / HU09) ----------


def test_pago_parcial_y_saldo_exacto(admin_api):
    _, inv = _cliente_y_factura(admin_api)
    res = admin_api.create_payment(
        {"invoice_id": inv["id"], "amount": D("400"), "method": "transferencia"},
        new_idempotency_key(),
    )
    assert not res.replayed
    assert res.data["invoice_balance"] == "600.00"
    assert res.data["invoice_status"] == "PARCIAL"


def test_reintento_con_la_misma_clave_no_duplica(admin_api):
    _, inv = _cliente_y_factura(admin_api)
    key = new_idempotency_key()
    data = {"invoice_id": inv["id"], "amount": D("400"), "method": "efectivo"}
    first = admin_api.create_payment(data, key)
    second = admin_api.create_payment(data, key)  # doble clic / corte de red
    assert second.replayed
    assert second.data["id"] == first.data["id"]
    pagos = admin_api.list_payments(invoice_id=inv["id"])
    assert pagos["total"] == 1


def test_sobrepago_requiere_confirmacion(admin_api):
    c, inv = _cliente_y_factura(admin_api)
    key = new_idempotency_key()
    data = {"invoice_id": inv["id"], "amount": D("1100"), "method": "transferencia"}
    with pytest.raises(ApiError) as exc:
        admin_api.create_payment(data, key)
    assert exc.value.code == "amount_exceeds_balance"
    # El usuario confirma: misma operación, misma clave, con allow_credit
    res = admin_api.create_payment(data | {"allow_credit": True}, key)
    assert res.data["amount"] == "1000.00"
    assert res.data["credit_amount"] == "100.00"
    assert res.data["invoice_status"] == "PAGADA"
    assert admin_api.client_credit(c["id"])["available"] == "100.00"


def test_operador_no_anula_pagos_y_admin_si(admin_api, operator_api):
    _, inv = _cliente_y_factura(admin_api)
    pago = admin_api.create_payment(
        {"invoice_id": inv["id"], "amount": D("400"), "method": "cheque"}, new_idempotency_key()
    ).data
    with pytest.raises(ApiError) as exc:
        operator_api.void_payment(pago["id"], "cheque rechazado")
    assert exc.value.status == 403
    anulado = admin_api.void_payment(pago["id"], "cheque rechazado")
    assert anulado["is_void"] is True
    assert anulado["invoice_balance"] == "1000.00"


# ---------- Saldo a favor ----------


def test_cobro_a_cuenta_e_imputacion(admin_api):
    c, inv = _cliente_y_factura(admin_api)
    credito = admin_api.create_credit(
        {"client_id": c["id"], "amount": D("300"), "method": "transferencia"},
        new_idempotency_key(),
    ).data
    assert credito["client_available"] == "300.00"
    pago = admin_api.apply_credit(inv["id"], D("250"), new_idempotency_key()).data
    assert pago["method"] == "saldo_a_favor"
    assert pago["invoice_balance"] == "750.00"
    assert admin_api.client_credit(c["id"])["available"] == "50.00"
    with pytest.raises(ApiError) as exc:
        admin_api.apply_credit(inv["id"], D("100"), new_idempotency_key())
    assert exc.value.code == "insufficient_credit"
    assert admin_api.list_credits(client_id=c["id"])["total"] == 1


# ---------- Inicio ----------


def test_resumen_de_inicio(admin_api):
    c, _ = _cliente_y_factura(admin_api, due="2026-10-20", number="V-1")  # vencida
    for n, due in (("S-1", "2026-10-30"), ("S-2", "2026-11-04"), ("L-1", "2026-12-15")):
        admin_api.create_invoice(
            {
                "client_id": c["id"],
                "invoice_number": n,
                "issue_date": date(2026, 10, 1),
                "due_date": date.fromisoformat(due),
                "amount": D("10"),
            }
        )
    resumen = load_home_summary(admin_api)
    assert resumen.overdue_count == 1
    assert resumen.overdue_balance == D("1000.00")
    assert resumen.due_soon_count == 2  # S-1 y S-2 vencen en los próximos 7 días
    assert resumen.due_soon_balance == D("20.00")
    assert resumen.total_receivable == D("1030.00")
    assert [i["invoice_number"] for i in resumen.upcoming] == ["S-1", "S-2"]
