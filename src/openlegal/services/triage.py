"""Inline triage runner.

Synchronously walks the lv.itsm.incident.triage process for a freshly-opened
case. The step sequence is hard-coded here but mirrors `process/triage.bpmn`
exactly — when Flowable is introduced in Phase 1.5, this runner gets replaced
by the real engine reading the same BPMN file. DMN tables remain canonical
either way (the local `dmn.evaluate` handler reads `dmn/*.json` at dispatch
time).

The runner is intentionally tolerant: if any step errors (typically a stub
returning unknown.uncategorized, or a real LLM failure), it logs the failure
into the steps[] list and continues with a sensible default. The case still
ends up triaged with a best-effort assignment.

Use with caution from inside an HTTP request — every step does flush()s but
no commit. The caller is responsible for transaction boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case
from openlegal.models.expert_group import ExpertGroup
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal
from openlegal.uapf.dispatcher import dispatch


UAPF_PACKAGE_ID = "lv.itsm.incident.triage"
UAPF_PACKAGE_VERSION = "0.2.0-phase1"


@dataclass
class TriageResult:
    case_id: uuid.UUID
    case_number: str
    classification: str | None = None
    priority: str | None = None
    ownership: str | None = None
    group_slug: str | None = None
    group_id: uuid.UUID | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

def infer_service_tier(normalized: dict[str, Any] | None, raw: dict[str, Any] | None) -> str:
    """Pick a service_tier code from signal payload.

    Phase 1 heuristic: hosts on demo.example are tier_1; everything else is tier_2.
    Phase 2 swaps this for a real ServiceTier lookup via the Connection
    that owns this signal, OR a host-pattern catalog.
    """
    payload = normalized or raw or {}
    host = (payload.get("host") or payload.get("hostname") or "").lower()
    if host.endswith(".demo.example") or "demo.example" in host:
        return "tier_1"
    return "tier_2"


def _host_domain(host: str | None) -> str | None:
    """Extract the registrable domain from a hostname (best-effort, no PSL)."""
    if not host:
        return None
    parts = host.strip().lower().split(".")
    if len(parts) <= 2:
        return host.strip().lower()
    # rtr-r1.demo.example -> demo.example
    return ".".join(parts[-2:])


async def _resolve_group_id(
    session: AsyncSession, org: Organization, slug: str | None,
) -> uuid.UUID | None:
    if not slug:
        return None
    stmt = select(ExpertGroup.id).where(
        ExpertGroup.org_id == org.id, ExpertGroup.slug == slug,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_triage_inline(
    session: AsyncSession,
    org: Organization,
    *,
    signal: Signal,
    case: Case,
    service_tier_code: str | None = None,
) -> TriageResult:
    """Drive the lv.itsm.incident.triage flow end-to-end.

    Returns a TriageResult summarizing what landed where. Errors in individual
    steps do not abort the flow — they are captured per-step and we keep
    walking with reasonable defaults.
    """
    if service_tier_code is None:
        service_tier_code = infer_service_tier(
            signal.normalized_payload, signal.raw_payload,
        )

    context = {
        "execution_id": None,  # ad-hoc inline run, no UAPFExecution row
        "uapf_package_id": UAPF_PACKAGE_ID,
        "uapf_package_version": UAPF_PACKAGE_VERSION,
        "case_id": str(case.id),
        "trace_id": f"triage-{case.case_number}",
    }

    result = TriageResult(case_id=case.id, case_number=case.case_number)

    # 1. intake.normalize
    r = await dispatch(
        session, org, capability_name="intake.normalize",
        inputs={"signal_id": str(signal.id)}, context=context,
    )
    result.steps.append(_step_summary("intake.normalize", r))
    normalized = (
        r.get("output", {}).get("normalized_payload")
        if r["status"] == "success"
        else (signal.normalized_payload or signal.raw_payload or {})
    ) or {}

    # 2. ai.classify
    r = await dispatch(
        session, org, capability_name="ai.classify",
        inputs={
            "case_id": str(case.id),
            "signal_id": str(signal.id),
            "payload": normalized,
        },
        context=context,
    )
    result.steps.append(_step_summary("ai.classify", r))
    classification = (
        r.get("output", {}).get("taxonomy_code")
        if r["status"] == "success"
        else "unknown.uncategorized"
    )
    result.classification = classification

    # 3. ai.suggest_priority
    r = await dispatch(
        session, org, capability_name="ai.suggest-priority",
        inputs={
            "case_id": str(case.id),
            "severity": normalized.get("severity") or "average",
            "service_tier": service_tier_code,
            "classification": classification,
        },
        context=context,
    )
    result.steps.append(_step_summary("ai.suggest_priority", r))
    ai_priority = (
        r.get("output", {}).get("priority")
        if r["status"] == "success" else "P4"
    )

    # 4. dmn.evaluate(priority)
    r = await dispatch(
        session, org, capability_name="dmn.evaluate",
        inputs={
            "package_id": UAPF_PACKAGE_ID,
            "decision_id": "priority",
            "case_id": str(case.id),
            "signal_id": str(signal.id),
            "inputs": {
                "severity": normalized.get("severity"),
                "service_tier": service_tier_code,
                "ai_suggested_priority": ai_priority,
                "classification": classification,
            },
        },
        context=context,
    )
    result.steps.append(_step_summary("dmn.evaluate(priority)", r))
    confirmed_priority = (
        r.get("output", {}).get("output", {}).get("priority")
        if r["status"] == "success" else ai_priority
    )
    result.priority = confirmed_priority

    # 5. dmn.evaluate(ownership)
    domain = _host_domain(normalized.get("host"))
    r = await dispatch(
        session, org, capability_name="dmn.evaluate",
        inputs={
            "package_id": UAPF_PACKAGE_ID,
            "decision_id": "ownership",
            "case_id": str(case.id),
            "inputs": {
                "classification": classification,
                "host_domain": domain,
                "source": signal.source.value,
            },
        },
        context=context,
    )
    result.steps.append(_step_summary("dmn.evaluate(ownership)", r))
    ownership = (
        r.get("output", {}).get("output", {}).get("ownership")
        if r["status"] == "success" else "own"
    )
    result.ownership = ownership

    # 6. dmn.evaluate(routing)
    r = await dispatch(
        session, org, capability_name="dmn.evaluate",
        inputs={
            "package_id": UAPF_PACKAGE_ID,
            "decision_id": "routing",
            "case_id": str(case.id),
            "inputs": {
                "classification": classification,
                "priority": confirmed_priority,
                "ownership": ownership,
            },
        },
        context=context,
    )
    result.steps.append(_step_summary("dmn.evaluate(routing)", r))
    group_slug = (
        r.get("output", {}).get("output", {}).get("group_slug")
        if r["status"] == "success" else "helpdesk-l1"
    )
    result.group_slug = group_slug

    # Resolve group_slug to a real ExpertGroup.id
    group_id = await _resolve_group_id(session, org, group_slug)
    result.group_id = group_id

    # 7. incident.update — apply decisions + transition open -> triaged
    patch: dict[str, Any] = {
        "priority": confirmed_priority,
        "ownership": ownership,
    }
    if group_id:
        patch["assigned_group_id"] = str(group_id)
    r = await dispatch(
        session, org, capability_name="incident.update",
        inputs={
            "case_id": str(case.id),
            "patch": patch,
            "status": "triaged",
            "reason": f"Auto-triaged by {UAPF_PACKAGE_ID} v{UAPF_PACKAGE_VERSION}",
        },
        context=context,
    )
    result.steps.append(_step_summary("incident.update", r))

    # 8. ai.draft_response (requires_human_approval=True; sits as a PROPOSED
    #    AIDecision until an operator approves via the UI)
    title = (normalized.get("title") or case.title or "incidents")[:120]
    r = await dispatch(
        session, org, capability_name="ai.draft-response",
        inputs={
            "case_id": str(case.id),
            "locale": "lv",
            "what_happened": title,
        },
        context=context,
    )
    result.steps.append(_step_summary("ai.draft_response", r))

    # 9. event.emit(routed) — closes out triage
    r = await dispatch(
        session, org, capability_name="event.emit",
        inputs={
            "case_id": str(case.id),
            "type": "routed",
            "payload": {
                "classification": classification,
                "priority": confirmed_priority,
                "ownership": ownership,
                "group_slug": group_slug,
            },
            "actor_label": f"uapf:{UAPF_PACKAGE_ID}",
        },
        context=context,
    )
    result.steps.append(_step_summary("event.emit", r))

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step_summary(name: str, r: dict[str, Any]) -> dict[str, Any]:
    """Compact per-step summary suitable for serialization."""
    out: dict[str, Any] = {
        "step": name,
        "status": r.get("status", "unknown"),
        "duration_ms": r.get("duration_ms"),
    }
    if r.get("status") != "success" and r.get("error"):
        out["error"] = r["error"]
    return out


# ---------------------------------------------------------------------------
# UAPF engine result -> TriageResult helper (Phase 1.5)
# ---------------------------------------------------------------------------

async def build_triage_result_from_case(
    session: AsyncSession,
    case: Case,
    invocations: list | None = None,
) -> "TriageResult":
    """Construct a TriageResult by reading the case's current persisted state.

    Used by the engine-driven code path in intake.py: when a UAPFSession
    completes, the case has been mutated by the engine's callbacks to our
    host handlers, so the binding decisions (priority, ownership, group)
    are already on the case row. `invocations` is the list of
    UAPFCapabilityInvocation rows from this run, mapped 1:1 to the
    TriageResult.steps array. Pass None to omit per-step traces.
    """
    # Load FK relationships fresh.
    await session.refresh(
        case, ["classification", "assigned_group", "service_tier"]
    )

    classification_code: str | None = None
    if case.classification is not None:
        classification_code = case.classification.code

    group_slug: str | None = None
    if case.assigned_group is not None:
        group_slug = case.assigned_group.slug

    steps_list: list[dict[str, Any]] = []
    if invocations:
        for inv in invocations:
            steps_list.append({
                "step": inv.capability_name,
                "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
                "duration_ms": inv.duration_ms,
                "error": inv.error_message,
            })

    return TriageResult(
        case_id=case.id,
        case_number=case.case_number,
        classification=classification_code,
        priority=case.priority.value if case.priority is not None else None,
        ownership=case.ownership.value if case.ownership is not None else None,
        group_slug=group_slug,
        group_id=case.assigned_group_id,
        steps=steps_list,
    )


__all__ = ["TriageResult", "run_triage_inline", "infer_service_tier", "build_triage_result_from_case"]
