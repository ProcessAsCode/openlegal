"""Incident service: open, transition, and timeline-append helpers.

Every state change to a Case goes through this module so the case_events
append-only timeline stays consistent. Callers do not write to case_events
directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case, CaseStatus
from openlegal.models.case_event import (
    CaseEvent,
    CaseEventActorType,
    CaseEventType,
)
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal, SignalStatus
from openlegal.services.case_numbering import allocate_case_number


# ---------------------------------------------------------------------------
# Open a new case (from a signal or from a manual create)
# ---------------------------------------------------------------------------

async def open_case_from_signal(
    session: AsyncSession,
    org: Organization,
    signal: Signal,
    *,
    title: str,
    description: str | None = None,
    actor_type: CaseEventActorType = CaseEventActorType.UAPF,
    actor_user_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    trace_id: str | None = None,
) -> Case:
    """Create a Case from a Signal, link them, append the initial events.

    Does not commit. The caller decides commit/rollback boundaries (the
    request-scoped session committer in `db.get_session` handles HTTP cases).

    Side effects:
      - Inserts a Case row with case_number allocated via the service.
      - Updates the Signal: status → opened_case, case_id set.
      - Appends two CaseEvent rows: signal_attached, status_changed→open.
    """
    now = datetime.now(timezone.utc)
    case_number = await allocate_case_number(session, org, now=now)

    case = Case(
        org_id=org.id,
        case_number=case_number,
        title=title,
        description=description,
        status=CaseStatus.OPEN,
        opened_at=now,
        state_snapshot={
            "opened_from_signal_id": str(signal.id),
            "source": signal.source.value,
        },
    )
    session.add(case)
    # Flush so case.id is assigned before we reference it on the events.
    await session.flush()

    # Link the signal to the new case.
    signal.case_id = case.id
    signal.status = SignalStatus.OPENED_CASE

    # Timeline: signal attached + initial status.
    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case.id,
            type=CaseEventType.SIGNAL_ATTACHED,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            trace_id=trace_id,
            payload={
                "signal_id": str(signal.id),
                "source": signal.source.value,
                "external_id": signal.external_id,
            },
        )
    )
    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case.id,
            type=CaseEventType.STATUS_CHANGED,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            trace_id=trace_id,
            payload={"from": None, "to": CaseStatus.OPEN.value},
        )
    )

    return case


async def open_case_manual(
    session: AsyncSession,
    org: Organization,
    *,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    classification_id: uuid.UUID | None = None,
    service_tier_id: uuid.UUID | None = None,
    actor_type: CaseEventActorType = CaseEventActorType.USER,
    actor_user_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    trace_id: str | None = None,
) -> Case:
    """Open a Case without an originating signal (manual operator path).

    Does not commit.
    """
    from openlegal.models.case import CasePriority  # local to avoid cycle

    now = datetime.now(timezone.utc)
    case_number = await allocate_case_number(session, org, now=now)

    case = Case(
        org_id=org.id,
        case_number=case_number,
        title=title,
        description=description,
        status=CaseStatus.OPEN,
        priority=CasePriority(priority) if priority else None,
        classification_id=classification_id,
        service_tier_id=service_tier_id,
        opened_at=now,
        state_snapshot={"opened_manually": True},
    )
    session.add(case)
    await session.flush()

    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case.id,
            type=CaseEventType.STATUS_CHANGED,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            trace_id=trace_id,
            payload={"from": None, "to": CaseStatus.OPEN.value},
        )
    )

    return case


# ---------------------------------------------------------------------------
# Transition a case to a new status
# ---------------------------------------------------------------------------

# Allowed transitions. Keys = current status; values = legal next statuses.
# Closed/cancelled are terminal in Phase 1 (Phase 2 will add a reopen path
# via a special event).
_ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.OPEN: {
        CaseStatus.TRIAGED,
        CaseStatus.IN_PROGRESS,
        CaseStatus.CANCELLED,
    },
    CaseStatus.TRIAGED: {
        CaseStatus.IN_PROGRESS,
        CaseStatus.WAITING_CUSTOMER,
        CaseStatus.WAITING_THIRD_PARTY,
        CaseStatus.RESOLVED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.IN_PROGRESS: {
        CaseStatus.WAITING_CUSTOMER,
        CaseStatus.WAITING_THIRD_PARTY,
        CaseStatus.RESOLVED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.WAITING_CUSTOMER: {
        CaseStatus.IN_PROGRESS,
        CaseStatus.RESOLVED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.WAITING_THIRD_PARTY: {
        CaseStatus.IN_PROGRESS,
        CaseStatus.RESOLVED,
        CaseStatus.CANCELLED,
    },
    CaseStatus.RESOLVED: {
        CaseStatus.CLOSED,
        CaseStatus.IN_PROGRESS,
    },
    CaseStatus.CLOSED: set(),
    CaseStatus.CANCELLED: set(),
}


class IllegalTransitionError(ValueError):
    """Raised when a case-status transition is not allowed by the FSM."""


async def transition_case(
    session: AsyncSession,
    case: Case,
    *,
    to_status: CaseStatus,
    reason: str | None = None,
    actor_type: CaseEventActorType = CaseEventActorType.USER,
    actor_user_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    trace_id: str | None = None,
) -> Case:
    """Transition a case to a new status, append a timeline event.

    Raises `IllegalTransitionError` if the transition is not allowed by the
    state machine.
    """
    current = case.status
    legal = _ALLOWED_TRANSITIONS.get(current, set())
    if to_status not in legal and to_status != current:
        raise IllegalTransitionError(
            f"Cannot transition from {current.value} to {to_status.value} "
            f"(legal: {sorted(s.value for s in legal)})"
        )

    if to_status == current:
        # No-op; do not append event.
        return case

    now = datetime.now(timezone.utc)
    from_status = current
    case.status = to_status

    # Set lifecycle timestamps when crossing relevant boundaries.
    if to_status == CaseStatus.TRIAGED and case.triaged_at is None:
        case.triaged_at = now
    elif to_status == CaseStatus.RESOLVED and case.resolved_at is None:
        case.resolved_at = now
    elif to_status == CaseStatus.CLOSED and case.closed_at is None:
        case.closed_at = now

    payload: dict[str, Any] = {
        "from": from_status.value,
        "to": to_status.value,
    }
    if reason:
        payload["reason"] = reason

    session.add(
        CaseEvent(
            org_id=case.org_id,
            case_id=case.id,
            type=CaseEventType.STATUS_CHANGED,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            trace_id=trace_id,
            payload=payload,
        )
    )
    return case


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

async def get_case_by_id(
    session: AsyncSession,
    org_id: uuid.UUID,
    case_id: uuid.UUID,
) -> Case | None:
    stmt = select(Case).where(Case.org_id == org_id).where(Case.id == case_id)
    return (await session.execute(stmt)).scalar_one_or_none()


__all__ = [
    "IllegalTransitionError",
    "get_case_by_id",
    "open_case_from_signal",
    "open_case_manual",
    "transition_case",
]
