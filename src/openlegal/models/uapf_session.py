"""UAPF outbound session tracking.

`UAPFSession` records one outbound call from OpenLegal to an external
UAPF engine. Created when `bridge.start_uapf_run` fires, updated as the
engine reports state. Separate table from `uapf_executions` /
`uapf_capability_invocations`:

  * UAPFExecution            - host-internal CMMN runs (no external engine)
  * UAPFCapabilityInvocation - engine -> host callbacks (one row per capability call)
  * UAPFSession              - host -> engine outbound runs (one row per start-session)

A Case may have many UAPFSession rows (e.g. one for triage, one for
follow-up customer response, one for retrospective). Each session may in
turn produce many UAPFCapabilityInvocation rows linked via `execution_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
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


class UAPFSessionState(StrEnum):
    """Lifecycle state of a UAPF engine session.

    Mirrors the values uapf-engine reports back. Includes a host-side-only
    `STARTING` for the brief window between persisting the row and the
    engine returning its first state.
    """

    STARTING = "starting"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class UAPFSession(
    UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base
):
    """One outbound run against an external UAPF engine."""

    __tablename__ = "uapf_sessions"

    # The session id returned by uapf-engine. Nullable while STARTING
    # (set as soon as the engine returns a sessionId).
    engine_session_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )

    # Which package + process + version we asked the engine to run.
    package_id: Mapped[str] = mapped_column(String(256), nullable=False)
    package_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_id: Mapped[str] = mapped_column(String(256), nullable=False)

    # Linkage to the entities that triggered this run.
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

    # Lifecycle.
    state: Mapped[UAPFSessionState] = mapped_column(
        Enum(UAPFSessionState, name="uapf_session_state", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UAPFSessionState.STARTING,
        index=True,
    )

    # Payloads + error.
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the engine reported terminal state.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional human-readable label for observability.
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- Relationships ---
    case: Mapped["Case | None"] = relationship("Case", lazy="joined")
    signal: Mapped["Signal | None"] = relationship("Signal", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<UAPFSession id={self.id} engine_session_id={self.engine_session_id!r} "
            f"package={self.package_id} state={self.state}>"
        )


__all__ = ["UAPFSession", "UAPFSessionState"]
