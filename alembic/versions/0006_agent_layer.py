"""agent layer: runs, steps, messages + UAS provenance on the register

Revision ID: 0006_agent_layer
Revises: 0005_ms_purview
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_agent_layer"
down_revision: Union[str, None] = "0005_ms_purview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planning"),
        sa.Column("agreement_ref", sa.String(128), nullable=True),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("steps_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scratchpad", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("allowed_capabilities", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("outcome", postgresql.JSONB(), nullable=True),
        sa.Column("halt_reason", sa.Text(), nullable=True),
        sa.Column("model_ref", sa.String(128), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_agreement_ref", "agent_runs", ["agreement_ref"])

    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False),
        sa.Column("thought", sa.Text(), nullable=True),
        sa.Column("offered_capabilities", postgresql.JSONB(), nullable=True),
        sa.Column("action_capability", sa.String(128), nullable=True),
        sa.Column("action_inputs", postgresql.JSONB(), nullable=True),
        sa.Column("observation", postgresql.JSONB(), nullable=True),
        sa.Column("guardrail_verdict", sa.String(32), nullable=True),
        sa.Column("guardrail_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_ref", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("signed_event_ref", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_steps_run_seq"),
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_interjection", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.add_column("legal_agreements", sa.Column("source_uas_id", sa.String(128), nullable=True))
    op.add_column("legal_agreements", sa.Column("uas_version", sa.Integer(), nullable=True))
    op.create_index("ix_legal_agreements_source_uas_id", "legal_agreements", ["source_uas_id"])


def downgrade() -> None:
    op.drop_index("ix_legal_agreements_source_uas_id", table_name="legal_agreements")
    op.drop_column("legal_agreements", "uas_version")
    op.drop_column("legal_agreements", "source_uas_id")
    op.drop_table("agent_messages")
    op.drop_table("agent_steps")
    op.drop_index("ix_agent_runs_agreement_ref", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_table("agent_runs")
