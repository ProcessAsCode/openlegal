"""incident UAPF capabilities: incident.fetch, incident.update."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case, CaseOwnership, CasePriority, CaseStatus
from openlegal.models.case_event import (
    CaseEvent,
    CaseEventActorType,
    CaseEventType,
)
from openlegal.models.organization import Organization


_PATCHABLE_FIELDS = {
    "priority", "ownership", "classification_id", "service_tier_id",
    "assigned_group_id", "assigned_user_id", "title", "description",
    "jira_mirror_key", "sla_first_response_due_at", "sla_resolution_due_at",
}


async def fetch(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"incident.fetch: case {case_id} not found in org {org.slug}")
    return _case_to_dict(case)


async def update(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"incident.update: case {case_id} not found in org {org.slug}")

    patch = inputs.get("patch") or {}
    if not isinstance(patch, dict):
        raise ValueError("incident.update: 'patch' must be a dict")

    applied: dict[str, Any] = {}
    for k, v in patch.items():
        if k not in _PATCHABLE_FIELDS:
            raise ValueError(f"incident.update: field {k!r} not patchable via UAPF")
        if k == "priority" and isinstance(v, str):
            v = CasePriority(v)
        elif k == "ownership" and isinstance(v, str):
            v = CaseOwnership(v)
        elif k in {"classification_id", "service_tier_id",
                   "assigned_group_id", "assigned_user_id"} and isinstance(v, str):
            v = uuid.UUID(v)
        elif k.endswith("_at") and isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        setattr(case, k, v)
        applied[k] = inputs["patch"][k]

    if applied:
        session.add(
            CaseEvent(
                org_id=org.id,
                case_id=case.id,
                type=_event_type_for_patch(applied),
                actor_type=CaseEventActorType.UAPF,
                actor_label=context.get("uapf_package_id"),
                trace_id=context.get("trace_id"),
                payload={"patch": applied},
            )
        )

    target_status = inputs.get("status")
    if target_status:
        from openlegal.services.incident import (
            IllegalTransitionError,
            transition_case,
        )
        try:
            await transition_case(
                session, case,
                to_status=CaseStatus(target_status),
                reason=inputs.get("reason"),
                actor_type=CaseEventActorType.UAPF,
                actor_label=context.get("uapf_package_id"),
                trace_id=context.get("trace_id"),
            )
        except IllegalTransitionError as exc:
            raise ValueError(f"incident.update: {exc}") from exc

    await session.flush()
    await session.refresh(case)
    return _case_to_dict(case)


def _event_type_for_patch(applied: dict[str, Any]) -> CaseEventType:
    if "priority" in applied:
        return CaseEventType.PRIORITIZED
    if "classification_id" in applied:
        return CaseEventType.CLASSIFIED
    if "assigned_group_id" in applied or "assigned_user_id" in applied:
        return CaseEventType.ASSIGNED
    if "ownership" in applied:
        return CaseEventType.OWNERSHIP_DECIDED
    return CaseEventType.OPERATOR_OVERRIDE


def _case_to_dict(case: Case) -> dict[str, Any]:
    def _id(v: Any) -> str | None:
        return str(v) if v is not None else None
    def _at(v: Any) -> str | None:
        return v.astimezone(timezone.utc).isoformat() if v else None
    return {
        "id": str(case.id),
        "org_id": str(case.org_id),
        "case_number": case.case_number,
        "title": case.title,
        "description": case.description,
        "status": case.status.value,
        "priority": case.priority.value if case.priority else None,
        "ownership": case.ownership.value if case.ownership else None,
        "classification_id": _id(case.classification_id),
        "service_tier_id": _id(case.service_tier_id),
        "assigned_group_id": _id(case.assigned_group_id),
        "assigned_user_id": _id(case.assigned_user_id),
        "jira_mirror_key": case.jira_mirror_key,
        "opened_at": _at(case.opened_at),
        "triaged_at": _at(case.triaged_at),
        "resolved_at": _at(case.resolved_at),
        "closed_at": _at(case.closed_at),
        "state_snapshot": case.state_snapshot or {},
    }
