"""VCReference model — local reference to a VC issued by the VeriDocs SDK.

OpenLegal never holds the full VC payload — that lives in the SDK / Register.
The VC reference row carries enough metadata (vc_id, type, subject, hash)
for the UI to display "this case has 17 attestations" and to fetch / verify
the full VC on demand.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
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


# The fixed set of VC types OpenLegal issues. Declared in the README under
# "VeriDocs DID/VC integration".
from enum import StrEnum


class VCType(StrEnum):
    """Catalog of VC types OpenLegal issues. Update README in lockstep."""

    INCIDENT_OPENED = "IncidentOpened"
    INCIDENT_CLASSIFIED = "IncidentClassified"
    INCIDENT_PRIORITIZED = "IncidentPrioritized"
    INCIDENT_ROUTED = "IncidentRouted"
    INCIDENT_ESCALATED = "IncidentEscalated"
    INCIDENT_STATUS_UPDATED = "IncidentStatusUpdated"
    COMMUNICATION_DRAFTED = "CommunicationDrafted"
    COMMUNICATION_APPROVED = "CommunicationApproved"
    COMMUNICATION_SENT = "CommunicationSent"
    INCIDENT_RESOLVED = "IncidentResolved"
    RETROSPECTIVE_COMPLETED = "RetrospectiveCompleted"
    INCIDENT_CLOSED = "IncidentClosed"
    AI_DECISION_ATTESTED = "AIDecisionAttested"
    DMN_EVALUATION_ATTESTED = "DMNEvaluationAttested"
    OPERATOR_OVERRIDE_ATTESTED = "OperatorOverrideAttested"
    PROCESS_PACKAGE_DEPLOYED = "ProcessPackageDeployed"


class VCReference(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """Pointer to a VC stored in the VeriDocs Register."""

    __tablename__ = "vc_references"

    # The VC's own id (issued by the SDK).
    vc_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    vc_type: Mapped[VCType] = mapped_column(
        Enum(VCType, name="vc_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    # DIDs involved.
    issuer_did: Mapped[str] = mapped_column(String(512), nullable=False)
    subject_did: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    # Cryptographic anchor — typically a SHA-256 of the VC payload.
    vc_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Convenience link back to the case this VC pertains to (most VC types
    # are case-scoped; ProcessPackageDeployed is org-scoped — case_id NULL).
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # SDK response payload (issuance receipt) — kept for audit.
    sdk_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Relationships
    case: Mapped["Case | None"] = relationship(back_populates="vc_references")
