"""Attachment model — files attached to a case.

OpenLegal doesn't manage file blobs itself by default. When OpenDMS is the
configured storage backend, the attachment row holds a reference to the
OpenDMS document; otherwise local disk / S3 / Azure paths.

Per the architecture decision: in deployments where OpenDMS is enabled,
ALL attachments go through OpenDMS so evidence + access control stays in
one place. The `storage_backend` field records which backend was used.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.case import Case
    from openlegal.models.user import User


class StorageBackend(StrEnum):
    """Where the file bytes live."""

    LOCAL = "local"
    S3 = "s3"
    AZURE = "azure"
    OPENDMS = "opendms"


class Attachment(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A file referenced from a case."""

    __tablename__ = "attachments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    storage_backend: Mapped[StorageBackend] = mapped_column(
        Enum(StorageBackend, name="storage_backend", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    # Backend-specific reference: filesystem path for LOCAL, key for S3/AZURE,
    # document GID/URI for OPENDMS.
    storage_ref: Mapped[str] = mapped_column(String(1024), nullable=False)

    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User | None"] = relationship()
