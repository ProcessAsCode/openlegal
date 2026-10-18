"""CaseEvent model — the append-only audit timeline for a case.

Everything that happens to a Case writes a row here: signal attached, AI
proposal created/approved/rejected, status changed, comment added, VC
issued, escalation triggered, etc. The frontend "Timeline" tab reads
straight from this table.

Events are never updated and never deleted. The Case row's snapshot
fields (status, priority, assignment) are derived from the latest
relevant event.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import Base, TenantScopedMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from openlegal.models.case import Case
    from openlegal.models.user import User
    from openlegal.models.vc_reference import VCReference


class CaseEventType(StrEnum):
    """Canonical event types written to the case timeline."""

    SIGNAL_ATTACHED = "signal_attached"
    NORMALIZED = "normalized"
    CLASSIFIED = "classified"
    PRIORITIZED = "prioritized"
    ROUTED = "routed"
    OWNERSHIP_DECIDED = "ownership_decided"
    ASSIGNED = "assigned"
    STATUS_CHANGED = "status_changed"
    PRIORITY_CHANGED = "priority_changed"
    AI_PROPOSAL_CREATED = "ai_proposal_created"
    AI_PROPOSAL_APPROVED = "ai_proposal_approved"
    AI_PROPOSAL_REJECTED = "ai_proposal_rejected"
    AI_PROPOSAL_APPLIED = "ai_proposal_applied"
    COMMENT_ADDED = "comment_added"
    CUSTOMER_REPLY_SENT = "customer_reply_sent"
    VC_ISSUED = "vc_issued"
    JIRA_SYNCED = "jira_synced"
    ESCALATED = "escalated"
    SLA_WARNING = "sla_warning"
    SLA_BREACHED = "sla_breached"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"
    UAPF_CAPABILITY_INVOKED = "uapf_capability_invoked"
    OPERATOR_OVERRIDE = "operator_override"


class CaseEventActorType(StrEnum):
    """Who or what caused this event."""

    SYSTEM = "system"
    USER = "user"
    AI = "ai"
    UAPF = "uapf"
    ADAPTER = "adapter"
    EXTERNAL = "external"


class CaseEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    """One row in the case's append-only timeline."""

    __tablename__ = "case_events"
    __table_args__ = (
        # Most-common timeline queries: "all events for a case, oldest first".
        Index("ix_case_events_case_id_created_at", "case_id", "created_at"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[CaseEventType] = mapped_column(
        Enum(CaseEventType, name="case_event_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    actor_type: Mapped[CaseEventActorType] = mapped_column(
        Enum(CaseEventActorType, name="case_event_actor_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    vc_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vc_references.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="events")
    actor_user: Mapped["User | None"] = relationship()
    vc_reference: Mapped["VCReference | None"] = relationship()
