"""Fechas de negocio: siempre en la zona configurada (America/Argentina/Buenos_Aires).

Los timestamps de auditoría se guardan en UTC (lo maneja PostgreSQL con timestamptz).
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().app_timezone)


def today_local() -> date:
    """Fecha "de hoy" para vencimientos y mora, en la zona de negocio."""
    return datetime.now(business_tz()).date()


def utcnow() -> datetime:
    return datetime.now(UTC)
