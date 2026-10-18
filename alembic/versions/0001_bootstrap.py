"""Phase 0 bootstrap: marker table only.

The real schema (organizations, users, cases, case_events, signals,
ai_decisions, dmn_evaluations, vc_references, ...) lands in 0002 during
the Phase 1 build. This migration exists so a fresh deployment has
something to migrate against, and so `alembic upgrade head` succeeds
on a clean Postgres.

Revision ID: 0001_bootstrap
Revises:
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_bootstrap"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "openlegal_meta",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO openlegal_meta (key, value) VALUES "
        "('schema_version', '0001_bootstrap'), "
        "('phase', 'phase-0-scaffold')"
    )


def downgrade() -> None:
    op.drop_table("openlegal_meta")
