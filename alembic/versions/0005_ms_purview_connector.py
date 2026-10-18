"""Add ms_purview to connection_kind enum.

Adds the Microsoft 365 / Purview Information Protection (MIP) connector kind so
the MIP-aware source adapter (the pilot's real docus.read decryption layer) can
hold a Connection row. PG 12+ permits ALTER TYPE ... ADD VALUE inside a
transaction as long as the new value is not used in the same transaction; this
migration only adds the label, so it is transaction-safe on the postgres:16 image.

Revision ID: 0005_ms_purview
Revises: 0004_agreement_register
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_ms_purview"
down_revision: Union[str, None] = "0004_agreement_register"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE connection_kind ADD VALUE IF NOT EXISTS 'ms_purview'")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE; removing an enum label is a
    # destructive type rebuild. Intentionally a no-op.
    pass
