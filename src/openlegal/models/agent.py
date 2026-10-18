"""Working memory of the agent: runs, steps, conversation turns.

These three tables are what turns OpenLegal from an executor of declared
UAPF sequences into an agent that chooses its next action at runtime — and
what makes that choice reconstructible afterwards. A step row is written
*before* its action executes, so a run that dies mid-action still explains
what it was attempting and why.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AgentRunStatus(StrEnum):
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"


class AgentStepPhase(StrEnum):
    OBSERVE = "observe"
    THINK = "think"
    ACT = "act"
    REFLECT = "reflect"
    HALT = "halt"


class GuardrailVerdict(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class AgentRun(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False,
                                        default=AgentRunStatus.PLANNING.value, index=True)
    agreement_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Hard stops, enforced in code.
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    steps_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scratchpad: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allowed_capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    halt_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentStep.seq")
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AgentMessage.created_at")


class AgentStep(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_agent_steps_run_seq"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    offered_capabilities: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    action_capability: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_inputs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    observation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    guardrail_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guardrail_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    model_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signed_event_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="steps")


class AgentMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_messages"

    run_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | agent | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_interjection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run: Mapped[AgentRun] = relationship(back_populates="messages")
