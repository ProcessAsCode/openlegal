"""ai.* UAPF capabilities.

Thin wrappers around the LLM client in openlegal.llm. Each handler:
  1. Extracts the relevant inputs.
  2. Calls the appropriate llm.* function (which tries the configured
     provider, falling back to a deterministic stub on any failure).
  3. Records an AIDecision row with the right approval-required flag.
  4. Returns {decision_id, ...llm-output...}.

The handler shape is unchanged from the pre-LLM version — same inputs,
same outputs, same AIDecision row contents — so the BPMN process and
inline triage runner don't need to know whether real Claude or the stub
produced the answer. The AIDecision.output `_via` field marks which path
ran ('anthropic' or 'stub'), useful for audit and demo verification.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.core.config import settings
from openlegal.llm import (
    classify_text,
    draft_response as llm_draft_response,
    extract_root_cause as llm_extract_root_cause,
    suggest_priority as llm_suggest_priority,
    summarize_timeline as llm_summarize_timeline,
)
from openlegal.models.ai_decision import AIDecision, AIDecisionStatus
from openlegal.models.organization import Organization


# ---------------------------------------------------------------------------
# Shared decision recorder
# ---------------------------------------------------------------------------

async def _record_decision(
    session: AsyncSession,
    org: Organization,
    *,
    capability: str,
    inputs: dict[str, Any],
    output: dict[str, Any],
    confidence: float | None,
    requires_human_approval: bool,
    case_id: str | None,
    signal_id: str | None,
    context: dict[str, Any],
) -> AIDecision:
    decision = AIDecision(
        org_id=org.id,
        case_id=uuid.UUID(case_id) if case_id else None,
        signal_id=uuid.UUID(signal_id) if signal_id else None,
        capability=capability,
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
        prompt_hash=hashlib.sha256(
            (capability + repr(inputs)).encode("utf-8")
        ).hexdigest()[:32],
        uapf_package_id=context.get("uapf_package_id"),
        uapf_package_version=context.get("uapf_package_version"),
        input=inputs,
        output=output,
        confidence=confidence,
        requires_human_approval=requires_human_approval,
        status=(
            AIDecisionStatus.PROPOSED
            if requires_human_approval
            else AIDecisionStatus.AUTO_APPLIED
        ),
        trace_id=context.get("trace_id"),
    )
    session.add(decision)
    await session.flush()
    return decision


def _extract_text(inputs: dict[str, Any]) -> str:
    if isinstance(inputs.get("text"), str):
        return inputs["text"]
    # Look through several possible keys in order; in engine-driven mode the
    # value for "normalized" may be a boolean flag (from intake.normalize's
    # output) rather than the payload dict — only accept actual dicts.
    payload: dict[str, Any] | None = None
    for key in ("payload", "normalized_payload", "normalized"):
        candidate = inputs.get(key)
        if isinstance(candidate, dict):
            payload = candidate
            break
    if payload is None:
        payload = {}
    parts = [
        payload.get("title") or "",
        payload.get("description") or "",
        payload.get("host") or "",
    ]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Capability handlers (slim wrappers around openlegal.llm.*)
# ---------------------------------------------------------------------------

async def classify(session, org, inputs, context):
    text = _extract_text(inputs)
    output = await classify_text(text)
    decision = await _record_decision(
        session, org, capability="ai.classify",
        inputs=inputs, output=output,
        confidence=output.get("confidence"),
        requires_human_approval=False,
        case_id=inputs.get("case_id"),
        signal_id=inputs.get("signal_id"),
        context=context,
    )
    return {"decision_id": str(decision.id), **output}


async def suggest_priority(session, org, inputs, context):
    output = await llm_suggest_priority(
        severity=inputs.get("severity"),
        service_tier=inputs.get("service_tier"),
        classification=inputs.get("classification"),
    )
    decision = await _record_decision(
        session, org, capability="ai.suggest_priority",
        inputs=inputs, output=output, confidence=0.8,
        requires_human_approval=False,
        case_id=inputs.get("case_id"),
        signal_id=inputs.get("signal_id"),
        context=context,
    )
    return {"decision_id": str(decision.id), **output}


async def draft_response(session, org, inputs, context):
    output = await llm_draft_response(
        org_slug=org.slug,
        what_happened=inputs.get("what_happened") or "incidents",
        eta_minutes=inputs.get("eta_minutes"),
        locale=(inputs.get("locale") or org.default_locale or "lv").lower(),
    )
    decision = await _record_decision(
        session, org, capability="ai.draft_response",
        inputs=inputs, output=output, confidence=0.7,
        requires_human_approval=True,
        case_id=inputs.get("case_id"),
        signal_id=None,
        context=context,
    )
    return {"decision_id": str(decision.id), **output}


async def summarize_timeline(session, org, inputs, context):
    events = inputs.get("events") or []
    output = await llm_summarize_timeline(events)
    decision = await _record_decision(
        session, org, capability="ai.summarize_timeline",
        inputs=inputs, output=output, confidence=0.6,
        requires_human_approval=False,
        case_id=inputs.get("case_id"),
        signal_id=None,
        context=context,
    )
    return {"decision_id": str(decision.id), **output}


async def extract_root_cause(session, org, inputs, context):
    text = _extract_text(inputs)
    output = await llm_extract_root_cause(text)
    decision = await _record_decision(
        session, org, capability="ai.extract_root_cause",
        inputs=inputs, output=output,
        confidence=output.get("confidence"),
        requires_human_approval=True,
        case_id=inputs.get("case_id"),
        signal_id=None,
        context=context,
    )
    return {"decision_id": str(decision.id), **output}


# -- agreement-monitoring: ai.classify_clause (deterministic, LLM-free) -------
_CLAUSE_KEYWORDS = {
    "payment": ["pay", "invoice", "amount"],
    "sla": ["sla", "uptime", "response", "availab"],
    "renewal": ["renew", "term", "extend"],
    "deliverable": ["deliver", "milestone"],
    "warranty": ["warrant", "defect"],
}


async def classify_clause(session, org, inputs, context):
    """Classify free-text clauses into obligation types. Deterministic keyword
    heuristic (reproducible; the algorithm card permits this fallback). If a
    clause already declares a type, that is trusted with confidence 1.0."""
    clauses = inputs.get("clauses")
    if clauses is None and inputs.get("agreement"):
        clauses = [
            {"id": o.get("id"), "text": o.get("rule") or o.get("type") or "",
             "type": o.get("type")}
            for o in (inputs["agreement"].get("obligations") or [])
        ]
    clauses = clauses or []
    out = []
    for cl in clauses:
        text = (cl.get("text") or "").lower()
        declared = cl.get("type")
        label = declared
        if not label:
            label = "other"
            for cat, kws in _CLAUSE_KEYWORDS.items():
                if any(k in text for k in kws):
                    label = cat
                    break
        out.append({"clause_id": cl.get("id"), "obligation_type": label,
                    "confidence": 1.0 if declared else 0.6,
                    "method": "declared" if declared else "keyword"})
    return {"classifications": out, "count": len(out)}
