"""La app Streamlit completa, ejecutada con streamlit.testing (sin navegador).

Corre donde Streamlit está instalado (tu PC y el CI); acá se saltea si no está.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

from app.seed import EXPECTED, seed_demo  # noqa: E402
from components.fmt import money, today_local  # noqa: E402
from tests.helpers import TEST_PASSWORD  # noqa: E402

pytestmark = pytest.mark.integration

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture
def demo_hoy(db, admin):
    # Fecha real: el dashboard y la API usan "hoy" en Buenos Aires.
    seed_demo(db, today_local(), admin)


def _login(at: AppTest, email: str, password: str) -> AppTest:
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button(key="login_button").click()
    return at.run()


def test_pide_login(wired):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.text_input(key="login_email") is not None
    assert len(at.metric) == 0


def test_login_incorrecto_muestra_error(wired, admin):
    at = AppTest.from_file(APP, default_timeout=60).run()
    _login(at, admin.email, "incorrecta")
    assert not at.exception
    assert "Email o contraseña incorrectos" in [e.value for e in at.error]


def test_kpis_coinciden_con_lo_documentado(wired, admin, demo_hoy):
    at = AppTest.from_file(APP, default_timeout=60).run()
    _login(at, admin.email, TEST_PASSWORD)
    assert not at.exception
    kpis = {m.label: m.value for m in at.metric}
    assert kpis["Saldo total por cobrar"] == money(EXPECTED["total_receivable"], decimals=False)
    assert kpis["Saldo vencido"] == "$ 625.000"
    assert kpis["% vencido"] == "71,02 %"
    assert kpis["Facturas vencidas"] == "6"
    assert kpis["Vence en 7 días"] == "$ 140.000"
    assert kpis["Saldo a favor disponible"] == "$ 20.000"
    assert kpis["Cobrado"] == "$ 1.425.000"  # últimos 12 meses


def test_filtro_por_cliente(wired, admin, demo_hoy):
    at = AppTest.from_file(APP, default_timeout=60).run()
    _login(at, admin.email, TEST_PASSWORD)
    at.selectbox(key="client").select("Constructora Andina SA").run()
    assert not at.exception
    kpis = {m.label: m.value for m in at.metric}
    assert kpis["Saldo total por cobrar"] == "$ 310.000"
    assert kpis["% vencido"] == "100,00 %"
