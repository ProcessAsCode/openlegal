"""Phase 1 schema: 18 tables for tenancy, configuration, incident core,
AI decisions, evidence (VC references), UAPF execution, and audit log.

Mirrors the SQLAlchemy models in `openlegal.models` 1:1 — see README "Data model"
section for the conceptual overview of each group.

Revision ID: 0002_phase1_schema
Revises: 0001_bootstrap
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0002_phase1_schema"
down_revision: Union[str, None] = "0001_bootstrap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Reusable column factories
# ---------------------------------------------------------------------------

def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _org_fk(nullable: bool = False) -> sa.Column:
    return sa.Column(
        "org_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=nullable,
        index=True,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        onupdate=sa.text("now()"),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Postgres ENUM types (created up-front so create_table references resolve)
# ---------------------------------------------------------------------------

USER_ROLE = postgresql.ENUM(
    "admin", "operator", "auditor", "service", name="user_role", create_type=False,
)
CONNECTION_KIND = postgresql.ENUM(
    "jira_dc", "jira_cloud", "zabbix", "email_imap", "email_smtp",
    "ldap", "opendms", "llm_gateway", name="connection_kind", create_type=False,
)
CONNECTION_STATUS = postgresql.ENUM(
    "active", "degraded", "error", "paused", name="connection_status", create_type=False,
)
SIGNAL_SOURCE = postgresql.ENUM(
    "zabbix", "email", "jira_dc", "jira_cloud", "phone", "manual", "api", "other",
    name="signal_source", create_type=False,
)
SIGNAL_STATUS = postgresql.ENUM(
    "received", "normalized", "deduped", "attached_to_case",
    "opened_case", "ignored", "failed", name="signal_status", create_type=False,
)
CASE_STATUS = postgresql.ENUM(
    "open", "triaged", "in_progress", "waiting_customer",
    "waiting_third_party", "resolved", "closed", "cancelled",
    name="case_status", create_type=False,
)
CASE_PRIORITY = postgresql.ENUM("P1", "P2", "P3", "P4", name="case_priority", create_type=False)
CASE_OWNERSHIP = postgresql.ENUM(
    "own", "not_own", "transferred", name="case_ownership", create_type=False,
)
CASE_EVENT_TYPE = postgresql.ENUM(
    "signal_attached", "normalized", "classified", "prioritized", "routed",
    "ownership_decided", "assigned", "status_changed", "priority_changed",
    "ai_proposal_created", "ai_proposal_approved", "ai_proposal_rejected",
    "ai_proposal_applied", "comment_added", "customer_reply_sent",
    "vc_issued", "jira_synced", "escalated", "sla_warning", "sla_breached",
    "resolved", "closed", "reopened", "uapf_capability_invoked",
    "operator_override", name="case_event_type", create_type=False,
)
CASE_EVENT_ACTOR_TYPE = postgresql.ENUM(
    "system", "user", "ai", "uapf", "adapter", "external",
    name="case_event_actor_type", create_type=False,
)
COMMENT_TYPE = postgresql.ENUM(
    "internal_note", "customer_reply_draft", "customer_reply_sent",
    "status_update", "third_party_note", name="comment_type", create_type=False,
)
STORAGE_BACKEND = postgresql.ENUM(
    "local", "s3", "azure", "opendms", name="storage_backend", create_type=False,
)
AI_DECISION_STATUS = postgresql.ENUM(
    "proposed", "auto_applied", "approved", "applied", "rejected",
    "expired", "failed", name="ai_decision_status", create_type=False,
)
VC_TYPE = postgresql.ENUM(
    "IncidentOpened", "IncidentClassified", "IncidentPrioritized",
    "IncidentRouted", "IncidentEscalated", "IncidentStatusUpdated",
    "CommunicationDrafted", "CommunicationApproved", "CommunicationSent",
    "IncidentResolved", "RetrospectiveCompleted", "IncidentClosed",
    "AIDecisionAttested", "DMNEvaluationAttested", "OperatorOverrideAttested",
    "ProcessPackageDeployed", name="vc_type", create_type=False,
)
UAPF_EXECUTION_STATUS = postgresql.ENUM(
    "running", "completed", "failed", "suspended", "cancelled",
    name="uapf_execution_status", create_type=False,
)
UAPF_INVOCATION_STATUS = postgresql.ENUM(
    "pending", "success", "error", "timeout", name="uapf_invocation_status", create_type=False,
)


ENUMS = [
    USER_ROLE, CONNECTION_KIND, CONNECTION_STATUS, SIGNAL_SOURCE, SIGNAL_STATUS,
    CASE_STATUS, CASE_PRIORITY, CASE_OWNERSHIP, CASE_EVENT_TYPE,
    CASE_EVENT_ACTOR_TYPE, COMMENT_TYPE, STORAGE_BACKEND, AI_DECISION_STATUS,
    VC_TYPE, UAPF_EXECUTION_STATUS, UAPF_INVOCATION_STATUS,
]


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # gen_random_uuid() comes from pgcrypto.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    # ---- organizations -----------------------------------------------------
    op.create_table(
        "organizations",
        _uuid_pk(),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("did", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_locale", sa.String(8), nullable=False, server_default="lv"),
        _created_at(),
        _updated_at(),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ---- users -------------------------------------------------------------
    op.create_table(
        "users",
        _uuid_pk(),
        _org_fk(),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", USER_ROLE, nullable=False, server_default="operator"),
        sa.Column("did", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("locale", sa.String(8), nullable=False, server_default="lv"),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_id_email"),
    )

    # ---- expert_groups -----------------------------------------------------
    op.create_table(
        "expert_groups",
        _uuid_pk(),
        _org_fk(),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duty_rotation_url", sa.String(512), nullable=True),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("org_id", "slug", name="uq_expert_groups_org_id_slug"),
    )

    # ---- expert_group_memberships -----------------------------------------
    op.create_table(
        "expert_group_memberships",
        sa.Column(
            "group_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("expert_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("membership_role", sa.String(32), nullable=False, server_default="member"),
        _created_at(),
        _updated_at(),
    )

    # ---- connections -------------------------------------------------------
    op.create_table(
        "connections",
        _uuid_pk(),
        _org_fk(),
        sa.Column("kind", CONNECTION_KIND, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secret_ref", sa.String(512), nullable=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("status", CONNECTION_STATUS, nullable=False, server_default="active"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
    )

    # ---- taxonomy_nodes ----------------------------------------------------
    op.create_table(
        "taxonomy_nodes",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"),
            nullable=True, index=True,
        ),
        sa.Column("code", sa.String(255), nullable=False, index=True),
        sa.Column("label_lv", sa.String(255), nullable=False),
        sa.Column("label_en", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("org_id", "code", name="uq_taxonomy_nodes_org_id_code"),
    )

    # ---- service_tiers -----------------------------------------------------
    op.create_table(
        "service_tiers",
        _uuid_pk(),
        _org_fk(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sla_first_response_minutes", sa.Integer, nullable=True),
        sa.Column("sla_resolution_minutes", sa.Integer, nullable=True),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("org_id", "code", name="uq_service_tiers_org_id_code"),
    )

    # ---- cases -------------------------------------------------------------
    op.create_table(
        "cases",
        _uuid_pk(),
        _org_fk(),
        sa.Column("case_number", sa.String(32), nullable=False, index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", CASE_STATUS, nullable=False, server_default="open", index=True),
        sa.Column("priority", CASE_PRIORITY, nullable=True, index=True),
        sa.Column("ownership", CASE_OWNERSHIP, nullable=True),
        sa.Column(
            "classification_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("taxonomy_nodes.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "service_tier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("service_tiers.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "assigned_group_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("expert_groups.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "assigned_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("jira_mirror_key", sa.String(64), nullable=True, index=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_first_response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sla_resolution_due_at", sa.DateTime(timezone=True),
            nullable=True, index=True,
        ),
        sa.Column(
            "state_snapshot", postgresql.JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("org_id", "case_number", name="uq_cases_org_id_case_number"),
    )

    # ---- signals -----------------------------------------------------------
    op.create_table(
        "signals",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "connection_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("connections.id", ondelete="RESTRICT"),
            nullable=True, index=True,
        ),
        sa.Column("source", SIGNAL_SOURCE, nullable=False, index=True),
        sa.Column("external_id", sa.String(255), nullable=True, index=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("normalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("dedupe_hash", sa.String(64), nullable=True, index=True),
        sa.Column("status", SIGNAL_STATUS, nullable=False, server_default="received", index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
    )

    # ---- vc_references -----------------------------------------------------
    op.create_table(
        "vc_references",
        _uuid_pk(),
        _org_fk(),
        sa.Column("vc_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("vc_type", VC_TYPE, nullable=False, index=True),
        sa.Column("issuer_did", sa.String(512), nullable=False),
        sa.Column("subject_did", sa.String(512), nullable=False, index=True),
        sa.Column("vc_hash", sa.String(128), nullable=True),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("sdk_response", postgresql.JSONB, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        _created_at(),
        _updated_at(),
    )

    # ---- ai_decisions ------------------------------------------------------
    op.create_table(
        "ai_decisions",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column("capability", sa.String(128), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False, server_default="anthropic"),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("uapf_package_id", sa.String(255), nullable=True),
        sa.Column("uapf_package_version", sa.String(64), nullable=True),
        sa.Column("input", postgresql.JSONB, nullable=False),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "requires_human_approval", sa.Boolean,
            nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "status", AI_DECISION_STATUS, nullable=False,
            server_default="proposed", index=True,
        ),
        sa.Column(
            "approved_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "vc_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vc_references.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        _created_at(),
        _updated_at(),
    )

    # ---- case_events -------------------------------------------------------
    op.create_table(
        "case_events",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("type", CASE_EVENT_TYPE, nullable=False, index=True),
        sa.Column("actor_type", CASE_EVENT_ACTOR_TYPE, nullable=False),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_label", sa.String(255), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        sa.Column(
            "payload", postgresql.JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "vc_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vc_references.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )
    op.create_index(
        "ix_case_events_case_id_created_at",
        "case_events", ["case_id", "created_at"],
    )

    # ---- dmn_evaluations ---------------------------------------------------
    op.create_table(
        "dmn_evaluations",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_id", sa.String(255), nullable=False, index=True),
        sa.Column("decision_version", sa.String(64), nullable=False),
        sa.Column("uapf_package_id", sa.String(255), nullable=True),
        sa.Column("uapf_package_version", sa.String(64), nullable=True),
        sa.Column("input", postgresql.JSONB, nullable=False),
        sa.Column("output", postgresql.JSONB, nullable=False),
        sa.Column(
            "matched_rules", postgresql.JSONB,
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("hit_policy", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "vc_reference_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vc_references.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        _created_at(),
        _updated_at(),
    )

    # ---- comments ----------------------------------------------------------
    op.create_table(
        "comments",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "author_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", COMMENT_TYPE, nullable=False, index=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_format", sa.Text(), nullable=False, server_default="markdown"),
        sa.Column(
            "ai_decision_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_decisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipients", postgresql.JSONB, nullable=True),
        _created_at(),
        _updated_at(),
    )

    # ---- attachments -------------------------------------------------------
    op.create_table(
        "attachments",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column(
            "mime_type", sa.String(255),
            nullable=False, server_default="application/octet-stream",
        ),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("storage_backend", STORAGE_BACKEND, nullable=False),
        sa.Column("storage_ref", sa.String(1024), nullable=False),
        sa.Column(
            "uploaded_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
        _updated_at(),
    )

    # ---- uapf_executions ---------------------------------------------------
    op.create_table(
        "uapf_executions",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "case_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("uapf_package_id", sa.String(255), nullable=False, index=True),
        sa.Column("uapf_package_version", sa.String(64), nullable=False),
        sa.Column("engine_execution_id", sa.String(255), nullable=True, index=True),
        sa.Column(
            "status", UAPF_EXECUTION_STATUS,
            nullable=False, server_default="running", index=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "variables", postgresql.JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        _created_at(),
        _updated_at(),
    )

    # ---- uapf_capability_invocations --------------------------------------
    op.create_table(
        "uapf_capability_invocations",
        _uuid_pk(),
        _org_fk(),
        sa.Column(
            "execution_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uapf_executions.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("capability_name", sa.String(128), nullable=False, index=True),
        sa.Column("capability_version", sa.String(16), nullable=False, server_default="1"),
        sa.Column("request_payload", postgresql.JSONB, nullable=False),
        sa.Column("response_payload", postgresql.JSONB, nullable=True),
        sa.Column(
            "status", UAPF_INVOCATION_STATUS,
            nullable=False, server_default="pending", index=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        _created_at(),
        _updated_at(),
    )

    # ---- audit_log ---------------------------------------------------------
    op.create_table(
        "audit_log",
        _uuid_pk(),
        sa.Column(
            "org_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "actor_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_label", sa.String(255), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True, index=True),
        sa.Column("action", sa.String(128), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=True, index=True),
        sa.Column("resource_id", sa.String(255), nullable=True, index=True),
        sa.Column(
            "payload", postgresql.JSONB,
            nullable=False, server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False, index=True,
        ),
    )

    # Stamp the marker table with the new schema version.
    op.execute(
        "INSERT INTO openlegal_meta (key, value) VALUES "
        "('schema_version', '0002_phase1_schema') "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Reverse order, then enums.
    for table in [
        "audit_log",
        "uapf_capability_invocations",
        "uapf_executions",
        "attachments",
        "comments",
        "dmn_evaluations",
        "case_events",
        "ai_decisions",
        "vc_references",
        "signals",
        "cases",
        "service_tiers",
        "taxonomy_nodes",
        "connections",
        "expert_group_memberships",
        "expert_groups",
        "users",
        "organizations",
    ]:
        op.drop_table(table)

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)

    op.execute(
        "UPDATE openlegal_meta SET value = '0001_bootstrap', updated_at = now() "
        "WHERE key = 'schema_version'"
    )
