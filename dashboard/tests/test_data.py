"""El dashboard muestra exactamente los valores documentados del dataset demo (HU06)."""

import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from app.seed import EXPECTED, month_start, seed_demo
from components.api import ApiError, DashboardApi, SessionExpired
from components.data import (
    Filters,
    debtor_rows,
    debtors_csv,
    load_dashboard,
    monthly_csv,
    upcoming_csv,
    upcoming_rows,
)
from tests.helpers import TEST_PASSWORD, set_today

pytestmark = pytest.mark.integration

HOY = date(2026, 10, 28)
D = Decimal


@pytest.fixture
def demo(db, admin):
    set_today(HOY)
    seed_demo(db, HOY, admin)


def _filtros(**kw) -> Filters:
    return Filters(date_from=kw.pop("date_from", month_start(HOY, 11)), date_to=HOY, **kw)


def test_vista_completa_coincide_con_lo_documentado(dash, demo):
    data = load_dashboard(dash, _filtros())
    o = data.overview
    assert D(o["total_receivable"]) == EXPECTED["total_receivable"]
    assert D(o["overdue_balance"]) == EXPECTED["overdue_balance"]
    assert D(o["collected"]) == sum(EXPECTED["monthly"].values())  # 12 meses
    assert len(data.monthly["items"]) == 12
    assert [d["client_name"] for d in data.debtors["items"]] == [
        name for name, _b, _o in EXPECTED["top_debtors"]
    ]
    assert [i["invoice_number"] for i in data.upcoming["items"]] == EXPECTED["upcoming_7"]
    assert not data.is_empty


def test_filtro_por_cliente_aplica_a_todo(dash, demo):
    andina = next(c for c in dash.all_clients() if "Andina" in c["name"])
    data = load_dashboard(dash, _filtros(client_id=andina["id"]))
    assert D(data.overview["total_receivable"]) == D("310000.00")
    assert [d["client_name"] for d in data.debtors["items"]] == ["Constructora Andina SA"]
    assert data.upcoming["count"] == 0


def test_tablas_formateadas(dash, demo):
    data = load_dashboard(dash, _filtros())
    assert debtor_rows(data)[0] == {
        "Cliente": "Constructora Andina SA",
        "Saldo": "$ 310.000,00",
        "Vencido": "$ 310.000,00",
        "Facturas": 2,
    }
    assert upcoming_rows(data)[0]["Vence"] == "28/10/2026"


def test_exportaciones_csv(dash, demo):
    data = load_dashboard(dash, _filtros())

    def rows(raw: bytes) -> list[list[str]]:
        text = raw.decode("utf-8")
        assert text.startswith("﻿")  # Excel en español abre bien los acentos
        return list(csv.reader(io.StringIO(text.lstrip("﻿"))))

    deudores = rows(debtors_csv(data))
    assert deudores[0] == ["cliente", "saldo", "saldo_vencido", "facturas"]
    assert deudores[1] == ["Constructora Andina SA", "310000.00", "310000.00", "2"]
    mensual = rows(monthly_csv(data))
    assert len(mensual) == 13 and mensual[-1][1] == "315000.00"
    proximos = rows(upcoming_csv(data))
    assert [r[1] for r in proximos[1:]] == EXPECTED["upcoming_7"]


def test_base_vacia(dash):
    set_today(HOY)
    data = load_dashboard(dash, _filtros())
    assert data.is_empty
    assert data.overview["overdue_pct"] is None


def test_login_incorrecto(wired, admin):
    client = DashboardApi("http://testserver/api/v1")
    with pytest.raises(ApiError) as exc:
        client.login(admin.email, "incorrecta")
    assert exc.value.message == "Email o contraseña incorrectos"


def test_sesion_se_renueva_y_luego_expira(dash, demo):
    dash._access = "vencido"
    assert dash.overview()["as_of"]  # renovó solo
    dash._access, dash._refresh = "vencido", "refresh-invalido-de-mas-de-20-caracteres"
    with pytest.raises(SessionExpired):
        dash.overview()
    assert not dash.is_authenticated


def test_logout(dash, api):
    refresh = dash._refresh
    dash.logout()
    assert not dash.is_authenticated
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_operador_puede_ver_el_dashboard(wired, operator, demo):
    client = DashboardApi("http://testserver/api/v1")
    client.login(operator.email, TEST_PASSWORD)
    assert load_dashboard(client, _filtros()).overview["overdue_count"] == 6
