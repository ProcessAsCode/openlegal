"""SQLAlchemy declarative base + shared mixins for OpenLegal models.

Conventions used across every model:
  * UUID primary keys (server-generated)
  * `created_at` + `updated_at` (UTC, server-defaulted)
  * Multi-tenant tables carry `org_id` and an index on it (TenantScopedMixin)
  * All datetime columns are timezone-aware
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)


class Base(DeclarativeBase):
    """Common base for all OpenLegal tables."""

    # Subclasses may override `__repr__` for nicer debug output;
    # default shows class name + primary key.
    def __repr__(self) -> str:  # pragma: no cover - debug helper
        pk_attr = next(iter(self.__mapper__.primary_key), None)
        pk_val = getattr(self, pk_attr.name, None) if pk_attr else None
        return f"<{type(self).__name__} id={pk_val}>"


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Adds `created_at` and `updated_at` (server-defaulted, timezone-aware)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Adds `org_id` foreign key to `organizations.id`, indexed.

    Use this on every per-tenant table so we can enforce tenant isolation
    in every query helper and so Alembic gets the index for free.
    """

    @declared_attr
    def org_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805 - SQLAlchemy convention
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )


# Public re-exports
__all__: list[str] = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "TenantScopedMixin",
]
