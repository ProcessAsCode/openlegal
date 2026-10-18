"""Expert groups (L1/L2/L3) and group membership.

The org organizes operators into level-based expert groups. Incidents route
to a group; on-call within the group is resolved by the duty rotation
(handled outside OpenLegal — Phase 1 references duty rotation by URL).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.user import User


class ExpertGroup(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A team that can be assigned ownership of an incident."""

    __tablename__ = "expert_groups"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_expert_groups_org_id_slug"),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional pointer to whatever system holds the duty rotation
    # (calendar URL, third-party scheduler API endpoint, etc.).
    duty_rotation_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationships
    memberships: Mapped[list["ExpertGroupMembership"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class ExpertGroupMembership(Base, TimestampMixin):
    """Join table for users ↔ expert_groups (many-to-many).

    Carries a `role` so we can mark group leads.
    """

    __tablename__ = "expert_group_memberships"

    group_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("expert_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    membership_role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")

    # Relationships
    group: Mapped["ExpertGroup"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="group_memberships")
