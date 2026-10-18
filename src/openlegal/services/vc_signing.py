"""Post-triage VC signing — anchors the key incident-lifecycle events
into the VeriDocs Register via the SDK sidecar.

Best-effort: if the SDK is unreachable, signing is skipped and triage
still completes. The case_events row remains; only its vc_reference_id
stays NULL.

Wired into `intake.py` after triage completes so all the events for the
case exist before we start signing.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal import sdk_client
from openlegal.models.case import Case
from openlegal.models.case_event import CaseEvent, CaseEventType
from openlegal.models.organization import Organization
from openlegal.models.vc_reference import VCReference, VCType

logger = logging.getLogger(__name__)


# Map CaseEventType -> VCType. Only the events on this list get signed —
# the others (status_changed, normalized, etc.) are operational chatter,
# not regulator-grade attestations.
_EVENT_TO_VC: dict[CaseEventType, VCType] = {
    CaseEventType.SIGNAL_ATTACHED:   VCType.INCIDENT_OPENED,
    CaseEventType.CLASSIFIED:        VCType.INCIDENT_CLASSIFIED,
    CaseEventType.PRIORITIZED:       VCType.INCIDENT_PRIORITIZED,
    CaseEventType.ROUTED:            VCType.INCIDENT_ROUTED,
    CaseEventType.OWNERSHIP_DECIDED: VCType.INCIDENT_ROUTED,
    CaseEventType.RESOLVED:          VCType.INCIDENT_RESOLVED,
    CaseEventType.CLOSED:            VCType.INCIDENT_CLOSED,
}


async def sign_triage_events(
    session: AsyncSession,
    org: Organization,
    case: Case,
) -> int:
    """Sign every signable case_event on this case that doesn't yet have a VC.

    Returns: count of newly-signed events.
    """
    # Fetch the events on this case that are in our signing whitelist
    # AND don't already have a VC reference attached.
    types = list(_EVENT_TO_VC.keys())
    stmt = (
        select(CaseEvent)
        .where(
            CaseEvent.case_id == case.id,
            CaseEvent.type.in_(types),
            CaseEvent.vc_reference_id.is_(None),
        )
        .order_by(CaseEvent.created_at.asc())
    )
    result = await session.execute(stmt)
    events: list[CaseEvent] = list(result.scalars().all())
    if not events:
        return 0

    signed_count = 0
    for ev in events:
        vc_type = _EVENT_TO_VC[ev.type]
        claims = _build_claims(case, ev)
        sdk_result = await sdk_client.sign_incident_event(
            case_number=case.case_number,
            event_type=vc_type.value,
            claims=claims,
            trace_id=ev.trace_id,
            actor={"label": ev.actor_label or "uapf"},
        )
        if not sdk_result:
            # SDK unreachable / error — best-effort; skip this event.
            continue

        vc_ref = VCReference(
            org_id=org.id,
            vc_id=sdk_result["vc_id"],
            vc_type=vc_type,
            issuer_did=sdk_result["issuer_did"],
            subject_did=sdk_result["subject_did"],
            vc_hash=sdk_result.get("vc_hash"),
            case_id=case.id,
            sdk_response=sdk_result.get("raw"),
            trace_id=ev.trace_id,
        )
        session.add(vc_ref)
        await session.flush()  # need vc_ref.id

        ev.vc_reference_id = vc_ref.id
        signed_count += 1

    if signed_count:
        await session.flush()
        logger.info(
            "VC signing: case=%s signed=%d/%d",
            case.case_number, signed_count, len(events),
        )
    return signed_count


def _build_claims(case: Case, ev: CaseEvent) -> dict[str, Any]:
    """Build the VC claims object for one event."""
    payload = ev.payload or {}
    base: dict[str, Any] = {
        "case_number": case.case_number,
        "case_id": str(case.id),
        "event_id": str(ev.id),
        "event_type": ev.type.value,
        "event_at": ev.created_at.isoformat() if ev.created_at else None,
        "actor_type": ev.actor_type.value if ev.actor_type else None,
        "actor_label": ev.actor_label,
    }
    # Pull the salient claims per event type so the VC carries them on-chain.
    if ev.type == CaseEventType.PRIORITIZED:
        base["priority"] = (payload.get("patch") or {}).get("priority") or case.priority.value if case.priority else None
    elif ev.type == CaseEventType.CLASSIFIED:
        base["classification_id"] = (payload.get("patch") or {}).get("classification_id")
    elif ev.type == CaseEventType.ROUTED:
        base["priority"] = payload.get("priority")
        base["ownership"] = payload.get("ownership")
        base["group_slug"] = payload.get("group_slug")
        base["classification"] = payload.get("classification")
    elif ev.type == CaseEventType.SIGNAL_ATTACHED:
        base["source"] = payload.get("source")
        base["external_id"] = payload.get("external_id")
    return base
