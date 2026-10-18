"""AuditLog model — generic security/admin audit trail.

Distinct from `case_events` (which is per-case business timeline):
`audit_log` records actions on system objects — user login, password
changes, connection create/update/delete, taxonomy edits, UAPF package
deployment, etc. The auditor role reads from this table; the operator
view typically does not surface it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from openlegal.models.user import User


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """One audit record.

    Not tenant-scoped via the mixin: a small number of admin actions are
    system-level (e.g. tenant provisioning) and have NULL org_id. Index on
    org_id is added explicitly.
    """

    __tablename__ = "audit_log"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Free-text actor when no User row exists (anonymous visitor, external
    # service, system action).
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Verb (e.g. "user.login", "case.created", "connection.deleted").
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    actor: Mapped["User | None"] = relationship()
