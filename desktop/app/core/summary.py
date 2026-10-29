"""Resumen de la pantalla Inicio a partir de /metrics (los mismos números del dashboard)."""

from dataclasses import dataclass, field
from decimal import Decimal

from desktop.app.core.formatting import to_decimal
from desktop.app.services.api import ApiClient

DUE_SOON_DAYS = 7


@dataclass
class HomeSummary:
    total_receivable: Decimal = Decimal("0.00")
    overdue_balance: Decimal = Decimal("0.00")
    overdue_count: int = 0
    due_soon_balance: Decimal = Decimal("0.00")
    due_soon_count: int = 0
    upcoming: list[dict] = field(default_factory=list)


def load_home_summary(api: ApiClient) -> HomeSummary:
    """KPIs "a hoy" (spec §6) y próximos vencimientos. "Hoy" lo define el servidor."""
    o = api.metrics_overview()
    u = api.metrics_upcoming(days=DUE_SOON_DAYS)
    return HomeSummary(
        total_receivable=to_decimal(o["total_receivable"]),
        overdue_balance=to_decimal(o["overdue_balance"]),
        overdue_count=o["overdue_count"],
        due_soon_balance=to_decimal(o["due_soon_balance"]),
        due_soon_count=o["due_soon_count"],
        upcoming=u["items"],
    )
