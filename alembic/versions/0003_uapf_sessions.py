"""Phase 1.5 - uapf_sessions table for outbound UAPF engine runs.

Adds the `uapf_sessions` table and the `uapf_session_state` enum.

One row per call from OpenLegal to an external UAPF engine
(`POST /uapf/start-session`). Separate from `uapf_executions` (host-internal
CMMN runs) and `uapf_capability_invocations` (engine -> host callbacks):
this table records the OUTBOUND side. A typical incident flow produces one
UAPFSession row (the triage process) which then produces N
UAPFCapabilityInvocation rows as the engine calls back for each capability.

Revision ID: 0003_uapf_sessions
Revises: 0002_phase1_schema
Create Date: 2026-06-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003_uapf_sessions"
down_revision: Union[str, None] = "0002_phase1_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SESSION_STATE_ENUM = postgresql.ENUM(
    "starting", "running", "suspended", "completed", "failed", "aborted",
    name="uapf_session_state",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    sa.Enum(
        "starting", "running", "suspended", "completed", "failed", "aborted",
        name="uapf_session_state",
    ).create(bind, checkfirst=True)

    op.create_table(
        "uapf_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("engine_session_id", sa.String(128), nullable=True),
        sa.Column("package_id", sa.String(256), nullable=False),
        sa.Column("package_version", sa.String(64), nullable=True),
        sa.Column("process_id", sa.String(256), nullable=False),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "state",
            SESSION_STATE_ENUM,
            nullable=False,
            server_default=sa.text("'starting'::uapf_session_state"),
        ),
        sa.Column("input_payload", postgresql.JSONB, nullable=True),
        sa.Column("output_payload", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_uapf_sessions_engine_session_id",
        "uapf_sessions",
        ["engine_session_id"],
    )
    op.create_index("ix_uapf_sessions_case_id", "uapf_sessions", ["case_id"])
    op.create_index("ix_uapf_sessions_signal_id", "uapf_sessions", ["signal_id"])
    op.create_index("ix_uapf_sessions_state", "uapf_sessions", ["state"])
    op.create_index("ix_uapf_sessions_package_id", "uapf_sessions", ["package_id"])

    op.execute(
        "UPDATE openlegal_meta SET value = '0003_uapf_sessions', updated_at = now() "
        "WHERE key = 'schema_version'"
    )


def downgrade() -> None:
    op.drop_table("uapf_sessions")
    bind = op.get_bind()
    sa.Enum(name="uapf_session_state").drop(bind, checkfirst=True)
    op.execute(
        "UPDATE openlegal_meta SET value = '0002_phase1_schema', updated_at = now() "
        "WHERE key = 'schema_version'"
    )
