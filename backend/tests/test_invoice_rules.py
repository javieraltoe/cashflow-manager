"""Tests unitarios de las reglas de negocio (spec §5). No usan base de datos."""

from datetime import date
from decimal import Decimal

import pytest

from app.services.invoice_rules import (
    InvoiceStatus,
    aging_bucket,
    balance,
    compute_status,
    days_overdue,
    money,
)

D = Decimal
HOY = date(2026, 10, 28)


class TestMontos:
    def test_decimal_es_exacto(self):
        assert money(D("0.10")) + money(D("0.20")) == D("0.30")

    def test_float_se_rechaza(self):
        with pytest.raises(TypeError):
            money(0.1)  # type: ignore[arg-type]

    def test_redondeo_a_centavos_half_up(self):
        assert money(D("10.005")) == D("10.01")
        assert money("125000.5") == D("125000.50")

    def test_saldo_es_importe_menos_pagos(self):
        assert balance(D("125000.50"), D("25000.25")) == D("100000.25")

    def test_saldo_sin_pagos_es_el_importe(self):
        assert balance(D("1000"), D("0")) == D("1000.00")


class TestEstado:
    @pytest.mark.parametrize(
        ("amount", "paid", "due", "esperado"),
        [
            # Sin pagos, no vencida -> PENDIENTE
            ("1000.00", "0", date(2026, 11, 5), InvoiceStatus.PENDIENTE),
            # Vence HOY: todavía no está vencida (vencimiento < hoy es estricto)
            ("1000.00", "0", HOY, InvoiceStatus.PENDIENTE),
            # Pago parcial, no vencida -> PARCIAL
            ("1000.00", "400.00", date(2026, 11, 5), InvoiceStatus.PARCIAL),
            # Venció ayer sin pagos -> VENCIDA
            ("1000.00", "0", date(2026, 10, 27), InvoiceStatus.VENCIDA),
            # Parcial y vencida -> VENCIDA (§5: se preserva el saldo real)
            ("1000.00", "400.00", date(2026, 10, 1), InvoiceStatus.VENCIDA),
            # Totalmente pagada (aunque esté vencida) -> PAGADA
            ("1000.00", "1000.00", date(2026, 10, 1), InvoiceStatus.PAGADA),
            ("1000.00", "1000.00", date(2026, 12, 1), InvoiceStatus.PAGADA),
        ],
    )
    def test_matriz_de_estados(self, amount, paid, due, esperado):
        assert compute_status(D(amount), D(paid), due, HOY) == esperado

    def test_anulada_tiene_prioridad(self):
        assert (
            compute_status(D("1000"), D("0"), date(2026, 1, 1), HOY, is_void=True)
            == InvoiceStatus.ANULADA
        )

    def test_pasa_a_vencida_sola_al_cambiar_el_dia(self):
        """HU05: misma factura, sin intervención manual, cambia de estado con la fecha."""
        due = date(2026, 10, 28)
        assert compute_status(D("500"), D("0"), due, date(2026, 10, 28)) == InvoiceStatus.PENDIENTE
        assert compute_status(D("500"), D("0"), due, date(2026, 10, 29)) == InvoiceStatus.VENCIDA


class TestMora:
    def test_dias_de_mora(self):
        assert days_overdue(D("100"), date(2026, 10, 18), HOY) == 10

    def test_sin_mora_si_no_vencio(self):
        assert days_overdue(D("100"), date(2026, 11, 18), HOY) == 0
        assert days_overdue(D("100"), HOY, HOY) == 0

    def test_sin_mora_si_no_hay_saldo(self):
        assert days_overdue(D("0"), date(2026, 1, 1), HOY) == 0

    @pytest.mark.parametrize(
        ("dias", "rango"),
        [
            (0, None),
            (1, "1-30"),
            (30, "1-30"),
            (31, "31-60"),
            (60, "31-60"),
            (61, "61-90"),
            (90, "61-90"),
            (91, "91+"),
            (400, "91+"),
        ],
    )
    def test_rangos_de_antiguedad(self, dias, rango):
        assert aging_bucket(dias) == rango
