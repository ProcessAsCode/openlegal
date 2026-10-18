"""Signal model — raw intake from any adapter.

Every Zabbix alert, every email, every Jira ticket creation, every phone-call
manual entry becomes a Signal row. The triage UAPF process decides whether to
open a fresh Case, attach to an existing Case, or drop as noise.

Signals are immutable once received; the normalization layer fills in
`normalized_at` + `normalized_payload` after parsing, but the raw payload
is preserved verbatim for evidence purposes.
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
    from openlegal.models.connection import Connection


class SignalSource(StrEnum):
    """Where the signal came from."""

    ZABBIX = "zabbix"
    EMAIL = "email"
    JIRA_DC = "jira_dc"
    JIRA_CLOUD = "jira_cloud"
    PHONE = "phone"
    MANUAL = "manual"
    API = "api"
    OTHER = "other"


class SignalStatus(StrEnum):
    """Lifecycle state."""

    RECEIVED = "received"
    NORMALIZED = "normalized"
    DEDUPED = "deduped"             # Suppressed as duplicate of existing signal/case
    ATTACHED_TO_CASE = "attached_to_case"
    OPENED_CASE = "opened_case"
    IGNORED = "ignored"             # Filtered out (e.g. routine_alert auto-ack)
    FAILED = "failed"


class Signal(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A single intake event."""

    __tablename__ = "signals"

    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source: Mapped[SignalSource] = mapped_column(
        Enum(SignalSource, name="signal_source", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Verbatim adapter payload — never mutated after insert.
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Normalized payload conforming to the OpenLegal signal schema (filled by
    # the `intake.normalize@1` UAPF capability).
    normalized_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    normalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # When non-null, this signal has been linked to a Case (existing or newly opened).
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Stable hash used by the triage process for dedupe across a time window.
    # Composed from (source, normalized.subject_key, normalized.host) or similar.
    dedupe_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, name="signal_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SignalStatus.RECEIVED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    connection: Mapped["Connection | None"] = relationship(back_populates="signals")
    case: Mapped["Case | None"] = relationship(back_populates="signals")
