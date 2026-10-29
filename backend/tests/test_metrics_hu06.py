"""HU06: el dashboard coincide con sumatorias SQL para datos de prueba documentados.

Tres fuentes tienen que coincidir:
1. Los valores documentados (app.seed.EXPECTED y docs/runbook/dataset-demo.md).
2. Lo que devuelven los endpoints /metrics (lo que muestra el dashboard).
3. Consultas SQL escritas a mano, independientes del código de la API (las mismas del doc).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.seed import EXPECTED, SeedError, month_start, seed_demo
from tests.helpers import set_today

pytestmark = pytest.mark.integration

HOY = date(2026, 10, 28)
URL = "/api/v1/metrics"
D = Decimal

# --- SQL independiente (copiado en docs/runbook/dataset-demo.md) ---
SQL_BALANCES = """
    SELECT i.id, i.client_id, i.due_date, i.amount - COALESCE(p.paid, 0) AS balance
    FROM invoices i
    LEFT JOIN (SELECT invoice_id, SUM(amount) AS paid FROM payments
               WHERE NOT is_void GROUP BY invoice_id) p ON p.invoice_id = i.id
    WHERE NOT i.is_void
"""
SQL_TOTAL = f"SELECT COALESCE(SUM(balance), 0) FROM ({SQL_BALANCES}) b"
SQL_OVERDUE = (
    f"SELECT COALESCE(SUM(balance), 0), COUNT(*) FROM ({SQL_BALANCES}) b "
    "WHERE due_date < :hoy AND balance > 0"
)
SQL_DUE_SOON = (
    f"SELECT COALESCE(SUM(balance), 0), COUNT(*) FROM ({SQL_BALANCES}) b "
    "WHERE due_date BETWEEN :hoy AND :hoy + 7 AND balance > 0"
)
SQL_COLLECTED = """
    SELECT (SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE NOT is_void AND method <> 'saldo_a_favor'
              AND payment_date BETWEEN :desde AND :hasta)
         + (SELECT COALESCE(SUM(amount), 0) FROM client_credits
            WHERE NOT is_void AND credit_date BETWEEN :desde AND :hasta)
"""
SQL_CREDIT_AVAILABLE = """
    SELECT (SELECT COALESCE(SUM(amount), 0) FROM client_credits WHERE NOT is_void)
         - (SELECT COALESCE(SUM(amount), 0) FROM payments
            WHERE NOT is_void AND method = 'saldo_a_favor')
"""


@pytest.fixture
def demo(db, admin):
    set_today(HOY)
    seed_demo(db, HOY, admin)


def _get(api, headers, path, **params):
    resp = api.get(f"{URL}/{path}", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _mes_actual():
    return {"date_from": HOY.replace(day=1).isoformat(), "date_to": HOY.isoformat()}


# ---------- 1 = 2: API vs valores documentados ----------


def test_overview_coincide_con_lo_documentado(api, admin_h, demo):
    o = _get(api, admin_h, "overview", **_mes_actual())
    assert o["as_of"] == HOY.isoformat()
    assert D(o["total_receivable"]) == EXPECTED["total_receivable"]
    assert D(o["overdue_balance"]) == EXPECTED["overdue_balance"]
    assert D(o["overdue_pct"]) == EXPECTED["overdue_pct"]
    assert o["overdue_count"] == EXPECTED["overdue_count"]
    assert D(o["due_soon_balance"]) == EXPECTED["due_soon_balance"]
    assert o["due_soon_count"] == EXPECTED["due_soon_count"]
    assert D(o["credit_available"]) == EXPECTED["credit_available"]
    assert D(o["collected"]) == EXPECTED["collected_current_month"]
    assert D(o["collected_payments"]) == EXPECTED["collected_payments_current_month"]
    assert D(o["collected_credits"]) == EXPECTED["collected_credits_current_month"]


def test_serie_mensual(api, admin_h, demo):
    desde = month_start(HOY, 5)
    m = _get(api, admin_h, "collections-monthly", date_from=desde.isoformat())
    meses = [p["month"] for p in m["items"]]
    assert meses == [month_start(HOY, k).strftime("%Y-%m") for k in range(5, -1, -1)]
    valores = [D(p["collected"]) for p in m["items"]]
    assert valores == [EXPECTED["monthly"][k] for k in range(5, -1, -1)]
    # Período por defecto: últimos 12 meses, con ceros donde no hubo cobros
    full = _get(api, admin_h, "collections-monthly")
    assert len(full["items"]) == 12
    assert D(full["total"]) == sum(EXPECTED["monthly"].values())


def test_aging(api, admin_h, demo):
    a = _get(api, admin_h, "aging")
    got = {b["bucket"]: (D(b["balance"]), b["count"]) for b in a["items"]}
    assert got == EXPECTED["aging"]
    assert D(a["total_overdue"]) == EXPECTED["overdue_balance"]


def test_top_deudores(api, admin_h, demo):
    t = _get(api, admin_h, "top-debtors")
    got = [(d["client_name"], D(d["balance"]), D(d["overdue_balance"])) for d in t["items"]]
    assert got == EXPECTED["top_debtors"]
    assert len(_get(api, admin_h, "top-debtors", limit=2)["items"]) == 2


def test_proximos_vencimientos(api, admin_h, demo):
    u = _get(api, admin_h, "upcoming")
    assert [i["invoice_number"] for i in u["items"]] == EXPECTED["upcoming_7"]
    assert D(u["total_balance"]) == EXPECTED["due_soon_balance"]
    assert u["count"] == EXPECTED["due_soon_count"]
    # Con 30 días entra también F-1002 (vence en 20 días, saldo 115.000)
    u30 = _get(api, admin_h, "upcoming", days=30)
    assert u30["count"] == 4
    assert D(u30["total_balance"]) == EXPECTED["due_soon_balance"] + D("115000.00")


# ---------- 2 = 3: API vs SQL independiente ----------


def test_api_coincide_con_sql_independiente(api, admin_h, demo, db_connection):
    def q(sql, **params):
        return db_connection.execute(text(sql), {"hoy": HOY} | params).one()

    o = _get(api, admin_h, "overview", **_mes_actual())
    assert D(o["total_receivable"]) == q(SQL_TOTAL)[0]
    overdue, overdue_n = q(SQL_OVERDUE)
    assert (D(o["overdue_balance"]), o["overdue_count"]) == (overdue, overdue_n)
    soon, soon_n = q(SQL_DUE_SOON)
    assert (D(o["due_soon_balance"]), o["due_soon_count"]) == (soon, soon_n)
    assert D(o["collected"]) == q(SQL_COLLECTED, desde=HOY.replace(day=1), hasta=HOY)[0]
    assert D(o["credit_available"]) == q(SQL_CREDIT_AVAILABLE)[0]


# ---------- Robustez ----------


@pytest.mark.parametrize(
    "hoy", [date(2026, 3, 1), date(2026, 12, 31), date(2027, 1, 15), date(2028, 2, 29)]
)
def test_los_valores_no_dependen_del_dia_de_carga(api, admin_h, db, admin, hoy):
    set_today(hoy)
    seed_demo(db, hoy, admin)
    period = {"date_from": hoy.replace(day=1).isoformat(), "date_to": hoy.isoformat()}
    o = _get(api, admin_h, "overview", **period)
    assert D(o["total_receivable"]) == EXPECTED["total_receivable"]
    assert D(o["overdue_balance"]) == EXPECTED["overdue_balance"]
    assert D(o["due_soon_balance"]) == EXPECTED["due_soon_balance"]
    assert D(o["collected"]) == EXPECTED["collected_current_month"]
    m = _get(api, admin_h, "collections-monthly", date_from=month_start(hoy, 5).isoformat())
    assert [D(p["collected"]) for p in m["items"]] == [
        EXPECTED["monthly"][k] for k in range(5, -1, -1)
    ]


def test_filtro_por_cliente(api, admin_h, demo):
    clientes = api.get("/api/v1/clients", headers=admin_h, params={"q": "Andina"}).json()
    cid = clientes["items"][0]["id"]
    o = _get(api, admin_h, "overview", client_id=cid, **_mes_actual())
    assert D(o["total_receivable"]) == D("310000.00")
    assert D(o["overdue_balance"]) == D("310000.00")
    assert D(o["overdue_pct"]) == D("100.00")
    assert D(o["collected"]) == D("20000.00")
    a = _get(api, admin_h, "aging", client_id=cid)
    assert {b["bucket"]: D(b["balance"]) for b in a["items"]} == {
        "1-30": D("0.00"),
        "31-60": D("250000.00"),
        "61-90": D("60000.00"),
        "91+": D("0.00"),
    }
    t = _get(api, admin_h, "top-debtors", client_id=cid)
    assert [d["client_name"] for d in t["items"]] == ["Constructora Andina SA"]


def test_base_vacia(api, admin_h):
    set_today(HOY)
    o = _get(api, admin_h, "overview")
    assert o["total_receivable"] == "0.00"
    assert o["overdue_pct"] is None  # la UI muestra N/D
    a = _get(api, admin_h, "aging")
    assert [b["balance"] for b in a["items"]] == ["0.00"] * 4
    m = _get(api, admin_h, "collections-monthly")
    assert {p["collected"] for p in m["items"]} == {"0.00"}


def test_periodo_invalido(api, admin_h):
    resp = api.get(
        f"{URL}/overview",
        headers=admin_h,
        params={"date_from": "2026-10-10", "date_to": "2026-10-01"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == "date_from"
    resp = api.get(
        f"{URL}/collections-monthly", headers=admin_h, params={"date_from": "2010-01-01"}
    )
    assert resp.status_code == 422


def test_operador_ve_metricas_y_anonimo_no(api, operator_h, demo):
    assert api.get(f"{URL}/overview", headers=operator_h).status_code == 200
    assert api.get(f"{URL}/overview").status_code == 401


def test_seed_no_pisa_datos_existentes(db, admin, demo):
    with pytest.raises(SeedError):
        seed_demo(db, HOY, admin)
    # --reset reemplaza todo y vuelve a cuadrar
    seed_demo(db, HOY + timedelta(days=1), admin, reset=True)
    total = db.execute(text(SQL_TOTAL)).scalar_one()
    assert total == EXPECTED["total_receivable"]


def test_bordes_de_los_rangos_de_antiguedad(api, admin_h):
    """30 d = 1-30; 31 y 60 = 31-60; 61 y 90 = 61-90; 91 = 91+; vence hoy = no vencida."""
    set_today(HOY)
    cid = api.post("/api/v1/clients", headers=admin_h, json={"name": "Bordes"}).json()["id"]
    for dias in (0, 1, 30, 31, 60, 61, 90, 91):
        due = HOY - timedelta(days=dias)
        resp = api.post(
            "/api/v1/invoices",
            headers=admin_h,
            json={
                "client_id": cid,
                "invoice_number": f"B-{dias}",
                "issue_date": (due - timedelta(days=1)).isoformat(),
                "due_date": due.isoformat(),
                "amount": f"{dias or 1000}.00",
            },
        )
        assert resp.status_code == 201
    a = _get(api, admin_h, "aging")
    got = {b["bucket"]: (b["balance"], b["count"]) for b in a["items"]}
    assert got == {
        "1-30": ("31.00", 2),  # 1 + 30
        "31-60": ("91.00", 2),  # 31 + 60
        "61-90": ("151.00", 2),  # 61 + 90
        "91+": ("91.00", 1),
    }
