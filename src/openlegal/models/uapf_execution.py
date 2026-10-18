"""UAPF execution tracking.

`UAPFExecution` — one row per CMMN case-execution run by the UAPF engine.
`UAPFCapabilityInvocation` — one row per callback from the engine to this
host (e.g. engine asks the host to satisfy `ai.classify@1` with this input).

Together they form the audit trail that lets us reconstruct exactly what
the engine did, what it called back, and what came out — which is the
substrate for both NIS2 evidence reports and operator debugging.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
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


class UAPFExecutionStatus(StrEnum):
    """Lifecycle state of a single execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class UAPFInvocationStatus(StrEnum):
    """Lifecycle state of a single capability callback."""

    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class UAPFExecution(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One CMMN case-execution by the UAPF engine."""

    __tablename__ = "uapf_executions"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    uapf_package_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    uapf_package_version: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_execution_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    status: Mapped[UAPFExecutionStatus] = mapped_column(
        Enum(UAPFExecutionStatus, name="uapf_execution_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UAPFExecutionStatus.RUNNING,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The variables / state the engine maintains for this execution.
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="uapf_executions")
    invocations: Mapped[list["UAPFCapabilityInvocation"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        order_by="UAPFCapabilityInvocation.started_at",
    )


class UAPFCapabilityInvocation(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One callback from the UAPF engine to this host."""

    __tablename__ = "uapf_capability_invocations"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("uapf_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    capability_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    capability_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")

    request_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[UAPFInvocationStatus] = mapped_column(
        Enum(UAPFInvocationStatus, name="uapf_invocation_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UAPFInvocationStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    execution: Mapped["UAPFExecution"] = relationship(back_populates="invocations")
