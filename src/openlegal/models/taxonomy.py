"""Taxonomy and service tiers — configuration that drives DMN decisions.

`TaxonomyNode` is a self-referencing tree of incident classifications. The
`ai.classify` capability picks a leaf; `routing.dmn` reads the leaf code +
service tier and produces the expert group.

`ServiceTier` defines SLA targets per service tier. Cases inherit the tier
from the signal source (Zabbix host group → service tier mapping) or from
an explicit setting on the connection.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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


class TaxonomyNode(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """One node of the classification tree.

    Code follows dotted-path convention, e.g.
        "network"
        "network.outage"
        "network.outage.link_down"
    """

    __tablename__ = "taxonomy_nodes"
    __table_args__ = (
        UniqueConstraint("org_id", "code", name="uq_taxonomy_nodes_org_id_code"),
    )

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("taxonomy_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label_lv: Mapped[str] = mapped_column(String(255), nullable=False)
    label_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Self-referential tree
    parent: Mapped["TaxonomyNode | None"] = relationship(
        remote_side="TaxonomyNode.id",
        back_populates="children",
    )
    children: Mapped[list["TaxonomyNode"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    # Inverse
    cases: Mapped[list["Case"]] = relationship(back_populates="classification")


class ServiceTier(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A service tier with SLA targets."""

    __tablename__ = "service_tiers"
    __table_args__ = (
        UniqueConstraint("org_id", "code", name="uq_service_tiers_org_id_code"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SLA targets in minutes (NULL = no SLA for this tier).
    sla_first_response_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_resolution_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Inverse
    cases: Mapped[list["Case"]] = relationship(back_populates="service_tier")
