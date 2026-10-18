"""Organization (tenant) model.

Each customer organisation has exactly one Organization. The Org's
DID is the issuer DID for every VC produced inside that tenant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from openlegal.models.case import Case
    from openlegal.models.user import User


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A tenant. One per customer deployment."""

    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    did: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Default locale for ops UI and customer comms. ISO-639-1 (lv, en, ...).
    default_locale: Mapped[str] = mapped_column(String(8), nullable=False, default="lv")

    # Relationships
    users: Mapped[list["User"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    cases: Mapped[list["Case"]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
