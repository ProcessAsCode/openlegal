"""User model: operators, admins, auditors.

Roles control what the user can do in the UI and which API endpoints they
can reach. The user's DID (did:key in Phase 1, eParaksts bridge in Phase 2)
is the actor on every signed VC the user authors or approves.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.expert_group import ExpertGroupMembership
    from openlegal.models.organization import Organization


class UserRole(StrEnum):
    """RBAC roles."""

    ADMIN = "admin"          # Full control over org settings, taxonomy, DMN, users
    OPERATOR = "operator"    # Work the queue, manage cases, approve AI proposals
    AUDITOR = "auditor"      # Read-only access to cases + audit trail
    SERVICE = "service"      # Non-human actor for adapter services


class User(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """An identity that can act inside an organization."""

    __tablename__ = "users"
    __table_args__ = (
        # Email is unique per organization, not globally — same email can exist
        # in two tenants if the customer ever has cross-deployment users.
        UniqueConstraint("org_id", "email", name="uq_users_org_id_email"),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.OPERATOR,
    )
    did: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Auth — Phase 1 uses local password hashing; Phase 2 will add SSO + eParaksts.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="lv")

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")
    group_memberships: Mapped[list["ExpertGroupMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
