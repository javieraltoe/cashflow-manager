"""Gráficos Plotly del dashboard.

Criterios (guía de visualización del proyecto):
- Una sola serie por gráfico -> un solo color (slot 1), sin leyenda: el título la nombra.
- Barras finas con puntas redondeadas de 4 px, grilla y ejes discretos, sin doble eje.
- Separadores argentinos (1.234,56) y tooltip con el monto exacto en pesos.
- Cada gráfico tiene su tabla equivalente en la página (accesibilidad y exportación).
"""

import plotly.graph_objects as go

from components.fmt import dec, money, month_label

SERIES_1 = "#2a78d6"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e8e7e3"
FONT = "Source Sans Pro, Segoe UI, sans-serif"


def _base_layout(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        separators=",.",  # decimal ',' y miles '.'
        font={"family": FONT, "color": TEXT_SECONDARY, "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        bargap=0.45,
        barcornerradius=4,
        hoverlabel={"bgcolor": "white", "font": {"color": TEXT_PRIMARY, "family": FONT}},
    )
    return fig


def _money_axis(axis: dict) -> dict:
    return axis | {
        "tickprefix": "$ ",
        "tickformat": ",.0f",
        "gridcolor": GRID,
        "zeroline": False,
        "rangemode": "tozero",
    }


def monthly_figure(items: list[dict]) -> go.Figure:
    """Cobrado por mes (flujo). items: [{month, collected, payments, credits}]."""
    x = [month_label(p["month"]) for p in items]
    y = [float(dec(p["collected"])) for p in items]  # Plotly dibuja con float; el texto no
    custom = [[money(p["collected"]), money(p["payments"]), money(p["credits"])] for p in items]
    fig = go.Figure(
        go.Bar(
            x=x,
            y=y,
            marker={"color": SERIES_1, "line": {"width": 0}},
            customdata=custom,
            hovertemplate=(
                "<b>%{x}</b><br>Cobrado: %{customdata[0]}<br>"
                "Pagos: %{customdata[1]}<br>Saldo a favor recibido: %{customdata[2]}"
                "<extra></extra>"
            ),
        )
    )
    _base_layout(fig)
    fig.update_xaxes(showgrid=False, tickfont={"color": TEXT_SECONDARY}, type="category")
    fig.update_yaxes(**_money_axis({}))
    return fig


def aging_figure(items: list[dict]) -> go.Figure:
    """Saldo vencido por antigüedad (stock). items: [{bucket, balance, count}]."""
    x = [f"{b['bucket']} días" for b in items]
    y = [float(dec(b["balance"])) for b in items]
    custom = [[money(b["balance"]), b["count"]] for b in items]
    fig = go.Figure(
        go.Bar(
            x=x,
            y=y,
            marker={"color": SERIES_1, "line": {"width": 0}},
            customdata=custom,
            hovertemplate=(
                "<b>%{x}</b><br>Vencido: %{customdata[0]}<br>Facturas: %{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )
    _base_layout(fig)
    fig.update_xaxes(showgrid=False, type="category")
    fig.update_yaxes(**_money_axis({}))
    return fig


def debtors_figure(items: list[dict]) -> go.Figure:
    """Principales deudores (stock), de mayor a menor de arriba hacia abajo."""
    names = [d["client_name"] for d in items]
    x = [float(dec(d["balance"])) for d in items]
    custom = [[money(d["balance"]), money(d["overdue_balance"]), d["invoice_count"]] for d in items]
    fig = go.Figure(
        go.Bar(
            x=x,
            y=names,
            orientation="h",
            marker={"color": SERIES_1, "line": {"width": 0}},
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>Saldo: %{customdata[0]}<br>Vencido: %{customdata[1]}"
                "<br>Facturas: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, height=max(220, 36 * len(items) + 40))
    fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
    fig.update_xaxes(**_money_axis({}))
    return fig
