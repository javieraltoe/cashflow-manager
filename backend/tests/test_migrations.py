"""Las migraciones de Alembic deben coincidir exactamente con los modelos ORM."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.db.base import Base

pytestmark = pytest.mark.integration


def test_modelos_y_migraciones_sin_diferencias(db_connection):
    ctx = MigrationContext.configure(db_connection, opts={"compare_type": True})
    diffs = compare_metadata(ctx, Base.metadata)
    assert diffs == [], f"Hay cambios sin migración: {diffs}"


def test_restricciones_clave_del_documento(db_connection):
    insp = inspect(db_connection)
    uniques = {u["name"] for u in insp.get_unique_constraints("invoices")}
    assert "uq_invoices_client_number" in uniques
    checks = {c["name"] for c in insp.get_check_constraints("invoices")}
    assert {"ck_invoices_amount_positive", "ck_invoices_currency_ars"} <= checks
    assert "ck_payments_amount_positive" in {
        c["name"] for c in insp.get_check_constraints("payments")
    }
    cols = {c["name"]: c for c in insp.get_columns("invoices")}
    assert str(cols["amount"]["type"]) == "NUMERIC(15, 2)"
