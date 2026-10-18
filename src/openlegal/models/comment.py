"""Comment model — internal notes and customer-facing replies.

Distinguishes:
  * `INTERNAL_NOTE`         — operators talking among themselves
  * `CUSTOMER_REPLY_DRAFT`  — AI-drafted reply awaiting operator approval
  * `CUSTOMER_REPLY_SENT`   — approved + sent
  * `STATUS_UPDATE`         — outbound status notification to customer
  * `THIRD_PARTY_NOTE`      — comment from external party (mirrored from Jira)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.ai_decision import AIDecision
    from openlegal.models.case import Case
    from openlegal.models.user import User


class CommentType(StrEnum):
    """Comment classification controlling visibility and outbound delivery."""

    INTERNAL_NOTE = "internal_note"
    CUSTOMER_REPLY_DRAFT = "customer_reply_draft"
    CUSTOMER_REPLY_SENT = "customer_reply_sent"
    STATUS_UPDATE = "status_update"
    THIRD_PARTY_NOTE = "third_party_note"


class Comment(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A single comment attached to a case."""

    __tablename__ = "comments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    type: Mapped[CommentType] = mapped_column(
        Enum(CommentType, name="comment_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_format: Mapped[str] = mapped_column(Text, nullable=False, default="markdown")

    # When the body was authored by AI, this references the originating decision.
    ai_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ai_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Approval gate (NULL while unapproved).
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Outbound delivery
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipients: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship(foreign_keys=[author_user_id])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by_user_id])
    ai_decision: Mapped["AIDecision | None"] = relationship()
