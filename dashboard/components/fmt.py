"""Formatos para Argentina: $ 1.234,56 y fechas dd/mm/aaaa."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
STATUS_LABELS = {
    "PENDIENTE": "Pendiente",
    "PARCIAL": "Parcial",
    "VENCIDA": "Vencida",
    "PAGADA": "Pagada",
    "ANULADA": "Anulada",
}


def today_local() -> date:
    return datetime.now(BUSINESS_TZ).date()


def dec(value: Decimal | str | int | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, float):
        raise TypeError("Los montos deben ser Decimal o str, nunca float")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(value: Decimal | str | int | None, decimals: bool = True) -> str:
    """'1234567.5' -> '$ 1.234.567,50' (o '$ 1.234.568' sin decimales)."""
    amount = dec(value)
    sign = "-" if amount < 0 else ""
    text = f"{abs(amount):,.2f}" if decimals else f"{abs(amount):,.0f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}$ {text}"


def pct(value: Decimal | str | None) -> str:
    if value is None:
        return "N/D"
    return f"{dec(value):.2f}".replace(".", ",") + " %"


def fdate(value: str | date | None) -> str:
    if not value:
        return ""
    d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return d.strftime("%d/%m/%Y")


def month_label(month: str) -> str:
    """'2026-10' -> 'oct 2026'."""
    year, m = month.split("-")
    return f"{MONTHS[int(m) - 1]} {year}"


def default_period(today: date, months: int = 12) -> tuple[date, date]:
    """Últimos `months` meses incluido el actual: (1° del mes, hoy)."""
    y, m = today.year, today.month - (months - 1)
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1), today
