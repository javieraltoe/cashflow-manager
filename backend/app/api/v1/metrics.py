"""GET /metrics/*: indicadores del dashboard (spec §6 y §9). Cualquier usuario autenticado."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, Today
from app.core.errors import AppError
from app.schemas.metrics import (
    Aging,
    CollectionsMonthly,
    Overview,
    Period,
    TopDebtors,
    Upcoming,
)
from app.services import metrics as metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"])

MAX_PERIOD_DAYS = 366 * 5
DEFAULT_MONTHS = 12


def default_from(today: date) -> date:
    """Primer día del mes, 11 meses atrás: los últimos 12 meses incluido el actual."""
    y, m = today.year, today.month - (DEFAULT_MONTHS - 1)
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1)


def period_params(
    today: Today,
    date_from: Annotated[
        date | None, Query(description="Inicio del período (por defecto, 12 meses atrás)")
    ] = None,
    date_to: Annotated[date | None, Query(description="Fin del período (por defecto, hoy)")] = None,
) -> Period:
    start = date_from or default_from(today)
    end = date_to or today
    if start > end:
        raise AppError(
            "validation_error",
            "La fecha 'desde' no puede ser posterior a 'hasta'",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "date_from",
        )
    if (end - start).days > MAX_PERIOD_DAYS:
        raise AppError(
            "validation_error",
            "El período no puede superar 5 años",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "date_from",
        )
    return Period(date_from=start, date_to=end)


PeriodQ = Annotated[Period, Depends(period_params)]
ClientQ = Annotated[uuid.UUID | None, Query(description="Filtrar por cliente")]


@router.get("/overview", response_model=Overview)
def overview(
    db: DbSession, _: CurrentUser, today: Today, period: PeriodQ, client_id: ClientQ = None
) -> Overview:
    """KPIs: saldo por cobrar, vencido, % vencido, próximos 7 días (a hoy) y cobrado (período)."""
    return metrics_service.overview(db, today, period, client_id)


@router.get("/collections-monthly", response_model=CollectionsMonthly)
def collections_monthly(
    db: DbSession, _: CurrentUser, period: PeriodQ, client_id: ClientQ = None
) -> CollectionsMonthly:
    """Cobrado por mes de la fecha de pago, con todos los meses del período (0 si no hubo)."""
    return metrics_service.collections_monthly(db, period, client_id)


@router.get("/aging", response_model=Aging)
def aging(db: DbSession, _: CurrentUser, today: Today, client_id: ClientQ = None) -> Aging:
    """Saldo vencido por antigüedad: 1–30, 31–60, 61–90 y 91+ días (a hoy)."""
    return metrics_service.aging(db, today, client_id)


@router.get("/top-debtors", response_model=TopDebtors)
def top_debtors(
    db: DbSession,
    _: CurrentUser,
    today: Today,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    client_id: ClientQ = None,
) -> TopDebtors:
    """Clientes con mayor saldo pendiente (a hoy)."""
    return metrics_service.top_debtors(db, today, limit, client_id)


@router.get("/upcoming", response_model=Upcoming)
def upcoming(
    db: DbSession,
    _: CurrentUser,
    today: Today,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    client_id: ClientQ = None,
) -> Upcoming:
    """Facturas no vencidas con saldo que vencen entre hoy y hoy + days."""
    return metrics_service.upcoming(db, today, days, client_id)
