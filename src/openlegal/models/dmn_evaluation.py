"""DMNEvaluation model — records every DMN table evaluation.

Distinct from AIDecision: DMN evaluations are *deterministic* — same input
in, same output out, no LLM in the loop. Recorded for evidence/audit and
so the operator UI can show "this case got priority P2 because rule #4 of
priority.dmn matched: source=zabbix, service_tier=tier_1, business_hours=true".
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
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
    from openlegal.models.vc_reference import VCReference


class DMNEvaluation(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One DMN evaluation = one decision-table run."""

    __tablename__ = "dmn_evaluations"

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
    )

    # Decision identification.
    decision_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    decision_version: Mapped[str] = mapped_column(String(64), nullable=False)
    uapf_package_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uapf_package_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Evaluation I/O
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Which rule(s) fired — list of rule numbers / IDs from the DMN table.
    matched_rules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    hit_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The VC issued for this evaluation (DMNEvaluationAttested), if any.
    vc_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vc_references.id", ondelete="SET NULL"),
        nullable=True,
    )

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    case: Mapped["Case | None"] = relationship(back_populates="dmn_evaluations")
    signal: Mapped["Signal | None"] = relationship()
    vc_reference: Mapped["VCReference | None"] = relationship()
