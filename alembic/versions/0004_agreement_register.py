"""Agreement Register.

Revision ID: 0004_agreement_register
Revises: 0003_uapf_sessions
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_agreement_register"
down_revision: Union[str, None] = "0003_uapf_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_agreements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("agreement_id", sa.String(128), nullable=False, index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status",
                  sa.Enum("active", "expired", "draft", "archived",
                          name="legal_agreement_status"),
                  nullable=False, server_default="active", index=True),
        sa.Column("source_docus_id", sa.String(128), nullable=True),
        sa.Column("source_sap_id", sa.String(128), nullable=True),
        sa.Column("uas", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "agreement_id",
                            name="uq_legal_agreements_org_aid"),
    )
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE connection_kind ADD VALUE IF NOT EXISTS 'docus_registry'")
        op.execute("ALTER TYPE connection_kind ADD VALUE IF NOT EXISTS 'sap_actuals'")


def downgrade() -> None:
    op.drop_table("legal_agreements")
    op.execute("DROP TYPE IF EXISTS legal_agreement_status")
