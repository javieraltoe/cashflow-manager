"""Modelo de la página: arma los datos de una vista filtrada y sus exportaciones CSV.

Sin Streamlit: se prueba contra la API real.
"""

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date

from components.api import DashboardApi
from components.fmt import STATUS_LABELS, dec, fdate, month_label


@dataclass
class Filters:
    date_from: date
    date_to: date
    client_id: str | uuid.UUID | None = None
    upcoming_days: int = 7


@dataclass
class DashboardData:
    filters: Filters
    overview: dict
    monthly: dict
    aging: dict
    debtors: dict
    upcoming: dict

    @property
    def is_empty(self) -> bool:
        o = self.overview
        return dec(o["total_receivable"]) == 0 and dec(self.monthly["total"]) == 0


def load_dashboard(api: DashboardApi, f: Filters) -> DashboardData:
    period = {"date_from": f.date_from, "date_to": f.date_to, "client_id": f.client_id}
    client = {"client_id": f.client_id}
    return DashboardData(
        filters=f,
        overview=api.overview(**period),
        monthly=api.collections_monthly(**period),
        aging=api.aging(**client),
        debtors=api.top_debtors(limit=10, **client),
        upcoming=api.upcoming(days=f.upcoming_days, **client),
    )


# ---------- Exportaciones (montos con punto decimal, sin símbolo: §10) ----------


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    # BOM: Excel en español abre bien los acentos.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def monthly_csv(data: DashboardData) -> bytes:
    return _csv(
        ["mes", "cobrado", "pagos", "saldo_a_favor_recibido"],
        [[p["month"], p["collected"], p["payments"], p["credits"]] for p in data.monthly["items"]],
    )


def aging_csv(data: DashboardData) -> bytes:
    return _csv(
        ["rango_dias", "saldo_vencido", "facturas"],
        [[b["bucket"], b["balance"], b["count"]] for b in data.aging["items"]],
    )


def debtors_csv(data: DashboardData) -> bytes:
    return _csv(
        ["cliente", "saldo", "saldo_vencido", "facturas"],
        [
            [d["client_name"], d["balance"], d["overdue_balance"], d["invoice_count"]]
            for d in data.debtors["items"]
        ],
    )


def upcoming_csv(data: DashboardData) -> bytes:
    return _csv(
        ["vencimiento", "factura", "cliente", "importe", "saldo", "estado"],
        [
            [
                i["due_date"],
                i["invoice_number"],
                i["client_name"],
                i["amount"],
                i["balance"],
                i["status"],
            ]
            for i in data.upcoming["items"]
        ],  # fmt: skip
    )


# ---------- Tablas para mostrar (texto ya formateado) ----------


def monthly_rows(data: DashboardData) -> list[dict]:
    from components.fmt import money

    return [
        {
            "Mes": month_label(p["month"]),
            "Cobrado": money(p["collected"]),
            "Pagos": money(p["payments"]),
            "Saldo a favor recibido": money(p["credits"]),
        }
        for p in data.monthly["items"]
    ]


def debtor_rows(data: DashboardData) -> list[dict]:
    from components.fmt import money

    return [
        {
            "Cliente": d["client_name"],
            "Saldo": money(d["balance"]),
            "Vencido": money(d["overdue_balance"]),
            "Facturas": d["invoice_count"],
        }
        for d in data.debtors["items"]
    ]


def upcoming_rows(data: DashboardData) -> list[dict]:
    from components.fmt import money

    return [
        {
            "Vence": fdate(i["due_date"]),
            "Factura": i["invoice_number"],
            "Cliente": i["client_name"],
            "Saldo": money(i["balance"]),
            "Estado": STATUS_LABELS.get(i["status"], i["status"]),
        }
        for i in data.upcoming["items"]
    ]
