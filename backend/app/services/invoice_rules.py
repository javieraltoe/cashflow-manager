"""Reglas de negocio de facturas (spec §5). Funciones puras, sin base de datos.

Todo monto es Decimal: pasar un float levanta TypeError a propósito.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class InvoiceStatus(StrEnum):
    PENDIENTE = "PENDIENTE"
    PARCIAL = "PARCIAL"
    VENCIDA = "VENCIDA"
    PAGADA = "PAGADA"
    # No figura en §5: estado de presentación para facturas anuladas (is_void).
    ANULADA = "ANULADA"


AGING_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("1-30", 1, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("91+", 91, None),
)


def money(value: Decimal | int | str) -> Decimal:
    """Normaliza a 2 decimales. Rechaza float para evitar errores de redondeo."""
    if isinstance(value, float):
        raise TypeError("Los montos deben ser Decimal, nunca float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def balance(amount: Decimal, paid: Decimal) -> Decimal:
    """Saldo pendiente = importe original − suma de pagos vigentes."""
    return money(amount) - money(paid)


def compute_status(
    amount: Decimal, paid: Decimal, due_date: date, today: date, is_void: bool = False
) -> InvoiceStatus:
    """PAGADA si saldo = 0; VENCIDA si saldo > 0 y vencimiento < hoy;
    PARCIAL si 0 < saldo < original y no vencida; PENDIENTE en los demás casos."""
    if is_void:
        return InvoiceStatus.ANULADA
    saldo = balance(amount, paid)
    if saldo <= ZERO:
        return InvoiceStatus.PAGADA
    if due_date < today:
        return InvoiceStatus.VENCIDA
    if saldo < money(amount):
        return InvoiceStatus.PARCIAL
    return InvoiceStatus.PENDIENTE


def days_overdue(saldo: Decimal, due_date: date, today: date) -> int:
    """max(0, hoy − vencimiento), solo si hay saldo pendiente."""
    if money(saldo) <= ZERO:
        return 0
    return max(0, (today - due_date).days)


def aging_bucket(days: int) -> str | None:
    """Rango de antigüedad de deuda vencida; None si no está vencida."""
    for label, low, high in AGING_BUCKETS:
        if days >= low and (high is None or days <= high):
            return label
    return None
