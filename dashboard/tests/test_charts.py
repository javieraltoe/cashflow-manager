"""Gráficos: una serie, un color, separadores argentinos y tooltip con montos exactos."""

import pytest

pytest.importorskip("plotly")

from components import charts  # noqa: E402

MONTHLY = [
    {"month": "2026-09", "collected": "300000.00", "payments": "300000.00", "credits": "0.00"},
    {"month": "2026-10", "collected": "315000.00", "payments": "290000.00", "credits": "25000.00"},
]
AGING = [
    {"bucket": "1-30", "balance": "120000.00", "count": 2},
    {"bucket": "31-60", "balance": "250000.00", "count": 1},
    {"bucket": "61-90", "balance": "60000.00", "count": 1},
    {"bucket": "91+", "balance": "195000.00", "count": 2},
]
DEBTORS = [
    {"client_name": "Constructora Andina SA", "balance": "310000.00",
     "overdue_balance": "310000.00", "invoice_count": 2},
    {"client_name": "Almacén Don Pepe", "balance": "185000.00",
     "overdue_balance": "70000.00", "invoice_count": 2},
]  # fmt: skip


def _common(fig):
    layout = fig.layout
    assert layout.separators == ",."
    assert layout.showlegend is False
    assert layout.barcornerradius == 4
    assert len(fig.data) == 1  # una sola serie
    assert fig.data[0].marker.color == charts.SERIES_1


def test_mensual():
    fig = charts.monthly_figure(MONTHLY)
    _common(fig)
    assert list(fig.data[0].x) == ["sep 2026", "oct 2026"]
    assert list(fig.data[0].y) == [300000.0, 315000.0]
    assert fig.data[0].customdata[1][2] == "$ 25.000,00"  # tooltip con texto exacto
    assert fig.layout.yaxis.tickprefix == "$ "


def test_antiguedad_respeta_el_orden():
    fig = charts.aging_figure(AGING)
    _common(fig)
    assert list(fig.data[0].x) == ["1-30 días", "31-60 días", "61-90 días", "91+ días"]


def test_deudores_horizontal_de_mayor_a_menor():
    fig = charts.debtors_figure(DEBTORS)
    _common(fig)
    assert fig.data[0].orientation == "h"
    assert list(fig.data[0].y) == ["Constructora Andina SA", "Almacén Don Pepe"]
    assert fig.layout.yaxis.autorange == "reversed"
    assert fig.data[0].customdata[1][1] == "$ 70.000,00"


def test_figuras_se_serializan():
    for fig in (
        charts.monthly_figure(MONTHLY),
        charts.aging_figure(AGING),
        charts.debtors_figure(DEBTORS),
    ):
        assert fig.to_json()
