from datetime import date
from decimal import Decimal

import pytest

from components.fmt import dec, default_period, fdate, money, month_label, pct


@pytest.mark.parametrize(
    ("value", "esperado"),
    [
        ("880000.00", "$ 880.000,00"),
        ("1234567.5", "$ 1.234.567,50"),
        ("0", "$ 0,00"),
        ("-1500", "-$ 1.500,00"),
        (None, "$ 0,00"),
    ],
)
def test_money(value, esperado):
    assert money(value) == esperado


def test_money_sin_decimales_redondea():
    assert money("1424999.50", decimals=False) == "$ 1.425.000"


def test_float_prohibido():
    with pytest.raises(TypeError):
        dec(0.1)  # type: ignore[arg-type]


def test_pct_y_nd():
    assert pct("71.02") == "71,02 %"
    assert pct(None) == "N/D"


def test_fechas_y_meses():
    assert fdate("2026-10-28") == "28/10/2026"
    assert month_label("2026-01") == "ene 2026"
    assert month_label("2025-12") == "dic 2025"


@pytest.mark.parametrize(
    ("hoy", "desde"),
    [
        (date(2026, 10, 28), date(2025, 11, 1)),
        (date(2026, 1, 15), date(2025, 2, 1)),
        (date(2026, 12, 31), date(2026, 1, 1)),
    ],
)
def test_periodo_por_defecto_12_meses(hoy, desde):
    assert default_period(hoy) == (desde, hoy)


def test_dec_cuantiza():
    assert dec("10.005") == Decimal("10.01")
