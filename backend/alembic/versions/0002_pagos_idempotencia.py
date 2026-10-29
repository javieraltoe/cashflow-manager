"""Pagos: clave de idempotencia para que un reintento no registre el cobro dos veces.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-29 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("idempotency_key", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_payments_idempotency_key"), "payments", ["idempotency_key"]
    )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_payments_idempotency_key"), "payments", type_="unique")
    op.drop_column("payments", "idempotency_key")
