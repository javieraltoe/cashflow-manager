"""Resumen de la pantalla Inicio, armado con los endpoints existentes.

Los KPIs monetarios (saldo total, vencido, cobrado) llegan con /metrics en el Sprint 4;
acá solo se muestran conteos y los próximos vencimientos.
"""

from dataclasses import dataclass, field
from datetime import date

from desktop.app.core.formatting import week_ahead
from desktop.app.services.api import ApiClient

UPCOMING_LIMIT = 50


@dataclass
class HomeSummary:
    overdue_count: int = 0
    due_soon_count: int = 0
    active_clients: int = 0
    upcoming: list[dict] = field(default_factory=list)


def load_home_summary(api: ApiClient, today: date) -> HomeSummary:
    overdue = api.list_invoices(status="VENCIDA", page_size=1)["total"]
    upcoming: list[dict] = []
    due_soon = 0
    # Facturas no vencidas con saldo que vencen entre hoy y hoy+7 (§6 "Próximos 7 días").
    for status in ("PENDIENTE", "PARCIAL"):
        page = api.list_invoices(
            status=status,
            due_from=today,
            due_to=week_ahead(today),
            sort="due_date",
            page_size=UPCOMING_LIMIT,
        )
        due_soon += page["total"]
        upcoming.extend(page["items"])
    upcoming.sort(key=lambda inv: (inv["due_date"], inv["invoice_number"]))
    clients = api.list_clients(is_active=True, page_size=1)["total"]
    return HomeSummary(
        overdue_count=overdue,
        due_soon_count=due_soon,
        active_clients=clients,
        upcoming=upcoming[:UPCOMING_LIMIT],
    )
