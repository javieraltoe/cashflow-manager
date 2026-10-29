from datetime import date
from decimal import Decimal

import pytest

from desktop.app.core.formatting import (
    format_date,
    format_datetime,
    format_money,
    money_for_input,
    parse_money,
    status_label,
)

D = Decimal


@pytest.mark.parametrize(
    ("value", "esperado"),
    [
        (D("0"), "$ 0,00"),
        (D("5.5"), "$ 5,50"),
        ("999.99", "$ 999,99"),
        ("1000", "$ 1.000,00"),
        ("125000.50", "$ 125.000,50"),
        ("1234567.89", "$ 1.234.567,89"),
        ("-1500", "-$ 1.500,00"),
        (None, ""),
    ],
)
def test_format_money(value, esperado):
    assert format_money(value) == esperado


def test_format_money_rechaza_float():
    with pytest.raises(TypeError):
        format_money(0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1234,56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("$ 1.234.567,8", "1234567.80"),
        ("1234.56", "1234.56"),  # punto con 2 decimales = decimal
        ("1.5", "1.50"),
        ("1.234", "1234.00"),  # punto con 3 dígitos = miles (uso argentino)
        ("12.345.678", "12345678.00"),
        ("125000", "125000.00"),
        (",5", "0.50"),
        ("  400 ", "400.00"),
    ],
)
def test_parse_money_valido(texto, esperado):
    assert parse_money(texto) == D(esperado)


@pytest.mark.parametrize(
    "texto",
    ["", "   ", "0", "0,00", "-10", "abc", "1,2,3", "10,555", "1e5", "99999999999999"],
)
def test_parse_money_invalido(texto):
    with pytest.raises(ValueError):
        parse_money(texto)


def test_ida_y_vuelta_input():
    assert parse_money(money_for_input("125000.50")) == D("125000.50")
    assert money_for_input("1000") == "1000,00"


def test_fechas():
    assert format_date("2026-10-30") == "30/10/2026"
    assert format_date(date(2026, 1, 5)) == "05/01/2026"
    assert format_date(None) == ""
    # 03:30 UTC = 00:30 en Buenos Aires
    assert format_datetime("2026-10-29T03:30:00+00:00") == "29/10/2026 00:30"


def test_etiquetas():
    assert status_label("VENCIDA") == "Vencida"
    assert status_label("DESCONOCIDO") == "DESCONOCIDO"
