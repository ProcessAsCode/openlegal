"""AIDecision model — records every AI-mediated decision step.

One row per `ai.*` UAPF capability invocation: classify, suggest_priority,
draft_response, summarize_timeline, extract_root_cause. Each row holds the
prompt hash (not the prompt itself — prompts are versioned in the UAPF
package), typed input + typed output, confidence, and the approval gate
metadata for human-in-the-loop policies.

When a VC is issued for the decision (capability `AIDecisionAttested`),
the VC reference is linked here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.case import Case
    from openlegal.models.signal import Signal
    from openlegal.models.user import User
    from openlegal.models.vc_reference import VCReference


class AIDecisionStatus(StrEnum):
    """Approval lifecycle."""

    PROPOSED = "proposed"        # AI produced output, awaiting human review
    AUTO_APPLIED = "auto_applied"  # Applied without approval (allowed by policy)
    APPROVED = "approved"        # Human approved but not yet applied
    APPLIED = "applied"          # Approved and the side-effect was taken
    REJECTED = "rejected"        # Human rejected the proposal
    EXPIRED = "expired"          # Timed out without decision
    FAILED = "failed"            # LLM call failed


class AIDecision(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One row per AI call."""

    __tablename__ = "ai_decisions"

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The UAPF capability that was invoked (e.g. "ai.classify").
    capability: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Provider + model identifiers.
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="anthropic")
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    # Hash of the rendered prompt (the actual prompt lives in the UAPF package
    # llm-tools.yaml; we record its hash + version for reproducibility).
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uapf_package_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uapf_package_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Typed I/O for this capability (schemas are declared in llm-tools.yaml).
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Human-in-the-loop policy
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[AIDecisionStatus] = mapped_column(
        Enum(AIDecisionStatus, name="ai_decision_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=AIDecisionStatus.PROPOSED,
        index=True,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The VC issued for this decision, when applicable.
    vc_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vc_references.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Trace ID linking this AI call to the originating request.
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    case: Mapped["Case | None"] = relationship(back_populates="ai_decisions")
    signal: Mapped["Signal | None"] = relationship()
    approver: Mapped["User | None"] = relationship()
    vc_reference: Mapped["VCReference | None"] = relationship()
