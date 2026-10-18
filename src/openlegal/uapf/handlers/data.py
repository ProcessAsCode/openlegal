"""data + event UAPF capabilities.

  data.write   - merge a JSON patch into a case's state_snapshot.
  event.emit   - append a typed event to the case timeline.
  dmn.evaluate - evaluate a DMN decision table and record the result.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case
from openlegal.models.case_event import (
    CaseEvent,
    CaseEventActorType,
    CaseEventType,
)
from openlegal.models.dmn_evaluation import DMNEvaluation
from openlegal.models.organization import Organization
from openlegal.uapf.dmn import DMNTable, evaluate


async def write(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    case_id = uuid.UUID(inputs["case_id"])
    patch = inputs.get("patch") or {}
    if not isinstance(patch, dict):
        raise ValueError("data.write: 'patch' must be a dict")
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"data.write: case {case_id} not found in org {org.slug}")
    merged = {**(case.state_snapshot or {}), **patch}
    case.state_snapshot = merged
    return {"case_id": str(case.id), "state_snapshot": merged}


async def event_emit(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"event.emit: case {case_id} not found in org {org.slug}")

    event_type = CaseEventType(inputs["type"])
    payload = inputs.get("payload") or {}

    event = CaseEvent(
        org_id=org.id,
        case_id=case.id,
        type=event_type,
        actor_type=CaseEventActorType.UAPF,
        actor_label=inputs.get("actor_label"),
        trace_id=context.get("trace_id"),
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return {"event_id": str(event.id), "type": event_type.value}


_DEFAULT_PACKAGE_ROOTS = [
    Path("uapf-packages"),
    Path("/srv/openlegal/uapf-packages"),
]


def _resolve_decision_path(package_id: str, decision_id: str) -> Path:
    for root in _DEFAULT_PACKAGE_ROOTS:
        candidate = root / package_id / "dmn" / f"{decision_id}.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"DMN decision {decision_id!r} not found under {package_id!r} "
        f"in any of: {[str(r) for r in _DEFAULT_PACKAGE_ROOTS]}"
    )


# BPMN stepId -> decision_id mapping for engine-driven mode where the BPMN
# doesn't carry the literal decision_id as a wired data input. Aligned with
# the lv.itsm.incident.triage v1.0.0 BPMN service task ids.
_STEP_TO_DECISION_ID: dict[str, str] = {
    "Task_EvaluatePriorityDmn": "priority",
    "Task_EvaluateOwnershipDmn": "ownership",
    "Task_EvaluateRoutingDmn": "routing",
}


async def dmn_evaluate(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    # Engine-driven mode: BPMN dataInputs are unbound, so engine sends synthetic
    # UUID placeholders for package_id / decision_id. Detect engine mode via the
    # presence of step_id in context and derive the real values from there.
    # Inline mode passes explicit string values directly.
    step_id = context.get("step_id") or ""
    if step_id in _STEP_TO_DECISION_ID:
        # Engine mode for one of our known DMN tasks
        package_id = "lv.itsm.incident.triage"
        decision_id = _STEP_TO_DECISION_ID[step_id]
    else:
        # Inline mode — runner passes explicit values
        package_id = inputs.get("package_id") or context.get("uapf_package_id") \
                     or "lv.itsm.incident.triage"
        decision_id = inputs.get("decision_id") or ""
        if not decision_id:
            raise KeyError(
                f"dmn.evaluate: decision_id missing from inputs AND step_id "
                f"{step_id!r} not in _STEP_TO_DECISION_ID"
            )
    raw_inputs = inputs.get("inputs")
    table_inputs = raw_inputs if isinstance(raw_inputs, dict) else {}

    path = _resolve_decision_path(package_id, decision_id)
    table = DMNTable.from_path(path)
    result = evaluate(table, table_inputs)

    case_uuid = uuid.UUID(inputs["case_id"]) if inputs.get("case_id") else None
    signal_uuid = uuid.UUID(inputs["signal_id"]) if inputs.get("signal_id") else None

    row = DMNEvaluation(
        org_id=org.id,
        case_id=case_uuid,
        signal_id=signal_uuid,
        decision_id=decision_id,
        decision_version="phase1",
        uapf_package_id=package_id,
        uapf_package_version=context.get("uapf_package_version", "phase1"),
        input=table_inputs,
        output=result.output,
        matched_rules=result.matched_rules,
        hit_policy=result.hit_policy,
        trace_id=context.get("trace_id"),
    )
    session.add(row)
    await session.flush()

    return {
        "evaluation_id": str(row.id),
        "output": result.output,
        "matched_rules": result.matched_rules,
        "hit_policy": result.hit_policy,
    }
