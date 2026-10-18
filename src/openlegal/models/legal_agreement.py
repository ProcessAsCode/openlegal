"""Agreement Register — UAS instances stored in the platform (NOT in the
process package). The package carries logic only; agreements are data and
live here, org-scoped. Sources (DOCUS/SAP) feed the register through the
conversion pipeline; the register is what governance monitoring iterates."""
from __future__ import annotations

import uuid

from sqlalchemy import Integer, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from openlegal.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

from enum import StrEnum


class AgreementStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DRAFT = "draft"
    ARCHIVED = "archived"


class LegalAgreement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One agreement in the register, carrying its full UAS document."""

    __tablename__ = "legal_agreements"
    __table_args__ = (UniqueConstraint("org_id", "agreement_id", name="uq_legal_agreements_org_aid"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    agreement_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[AgreementStatus] = mapped_column(
        Enum(AgreementStatus, name="legal_agreement_status",
             values_callable=lambda x: [e.value for e in x]),
        nullable=False, default=AgreementStatus.ACTIVE, index=True,
    )
    source_docus_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_sap_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Derived-view provenance: which e-Līgumi store row/version this mirrors.
    source_uas_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    uas_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uas: Mapped[dict] = mapped_column(JSONB, nullable=False)
