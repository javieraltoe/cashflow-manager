"""Formatos para Argentina: moneda ARS, fechas dd/mm/aaaa y etiquetas en español.

Los montos se manejan siempre como Decimal (la API los envía como string).
"""

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

BUSINESS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
CENT = Decimal("0.01")

STATUS_LABELS = {
    "PENDIENTE": "Pendiente",
    "PARCIAL": "Parcial",
    "VENCIDA": "Vencida",
    "PAGADA": "Pagada",
    "ANULADA": "Anulada",
}
METHOD_LABELS = {
    "efectivo": "Efectivo",
    "transferencia": "Transferencia",
    "cheque": "Cheque",
    "tarjeta": "Tarjeta",
    "deposito": "Depósito",
    "otro": "Otro",
    "saldo_a_favor": "Saldo a favor",
}
# Medios que el usuario puede elegir al registrar un cobro (sin el interno).
PAYMENT_METHODS = ["transferencia", "efectivo", "cheque", "tarjeta", "deposito", "otro"]
ROLE_LABELS = {"admin": "Administrador", "operator": "Operador"}
ORIGIN_LABELS = {"excedente": "Excedente de pago", "a_cuenta": "Cobro a cuenta"}


def today_local() -> date:
    return datetime.now(BUSINESS_TZ).date()


def week_ahead(today: date) -> date:
    return today + timedelta(days=7)


# ---------- Moneda ----------


def to_decimal(value: Decimal | str | int | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, float):
        raise TypeError("Los montos deben ser Decimal o str, nunca float")
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def format_money(value: Decimal | str | int | None, symbol: bool = True) -> str:
    """Decimal('1234567.5') -> '$ 1.234.567,50'."""
    if value is None or value == "":
        return ""
    amount = to_decimal(value)
    sign = "-" if amount < 0 else ""
    integer, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    body = f"{'.'.join(groups)},{cents}"
    return f"{sign}$ {body}" if symbol else f"{sign}{body}"


_MONEY_CHARS = re.compile(r"^[0-9.,]+$")


def parse_money(text: str) -> Decimal:
    """Interpreta lo que escribe el usuario. Acepta '1.234,56', '1234,56', '1234.56', '$ 1.234'.

    Regla: si hay coma, la coma es el decimal y los puntos son miles. Si solo hay un punto
    seguido de 1 o 2 dígitos, es el decimal; cualquier otro punto es separador de miles.
    """
    raw = (text or "").replace("$", "").replace(" ", "").strip()
    if not raw:
        raise ValueError("Ingresá un importe")
    if raw.startswith("-"):
        raise ValueError("El importe debe ser mayor a cero")
    if not _MONEY_CHARS.match(raw):
        raise ValueError("El importe solo puede tener números, puntos y una coma")
    if "," in raw:
        if raw.count(",") > 1:
            raise ValueError("El importe tiene más de una coma decimal")
        integer, decimals = raw.split(",")
        integer = integer.replace(".", "")
    elif raw.count(".") == 1 and len(raw.split(".")[1]) in (1, 2):
        integer, decimals = raw.split(".")
    else:
        integer, decimals = raw.replace(".", ""), ""
    if len(decimals) > 2:
        raise ValueError("El importe admite como máximo 2 decimales")
    if not integer and not decimals:
        raise ValueError("Ingresá un importe")
    try:
        value = Decimal(f"{integer or '0'}.{decimals or '0'}").quantize(CENT)
    except InvalidOperation as exc:
        raise ValueError("Importe inválido") from exc
    if value <= 0:
        raise ValueError("El importe debe ser mayor a cero")
    if value >= Decimal("10000000000000"):
        raise ValueError("El importe es demasiado grande")
    return value


def money_for_input(value: Decimal | str | None) -> str:
    """Valor para precargar un campo editable: '1234,50' (sin símbolo ni miles)."""
    if value is None or value == "":
        return ""
    return f"{to_decimal(value):.2f}".replace(".", ",")


# ---------- Fechas ----------


def parse_api_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def format_date(value: str | date | None) -> str:
    d = parse_api_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def format_datetime(value: str | datetime | None) -> str:
    """Timestamp UTC de la API -> 'dd/mm/aaaa hh:mm' en hora de Buenos Aires."""
    if not value:
        return ""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(BUSINESS_TZ)
    return dt.strftime("%d/%m/%Y %H:%M")


def status_label(code: str | None) -> str:
    return STATUS_LABELS.get(code or "", code or "")


def method_label(code: str | None) -> str:
    return METHOD_LABELS.get(code or "", code or "")


def role_label(code: str | None) -> str:
    return ROLE_LABELS.get(code or "", code or "")
