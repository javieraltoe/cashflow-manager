"""Tests de integración con PostgreSQL real (se saltean si la base no está arriba)."""

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def test_postgres_responde_y_es_version_16_o_superior(db_connection):
    version = db_connection.execute(text("SHOW server_version_num")).scalar_one()
    assert int(version) >= 160000


def test_sesion_en_utc(db_connection):
    # Regla del documento: timestamps de auditoría en UTC.
    assert db_connection.execute(text("SHOW timezone")).scalar_one() == "UTC"


def test_numeric_conserva_precision_exacta(db_connection):
    # Regla del documento: dinero en NUMERIC/Decimal, jamás float.
    from decimal import Decimal

    total = db_connection.execute(
        text("SELECT CAST('0.10' AS NUMERIC(15,2)) + CAST('0.20' AS NUMERIC(15,2))")
    ).scalar_one()
    assert total == Decimal("0.30")
