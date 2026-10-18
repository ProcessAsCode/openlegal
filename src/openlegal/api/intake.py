"""Intake router.

Adapters (Zabbix, email, Jira DC, Jira Cloud, manual entry) POST normalized
or raw signals here. Phase 1 flow inside this endpoint:

  1. INSERT Signal
  2. open_case_from_signal  - emits signal_attached + initial status_changed
  3. run_triage_inline      - walks lv.itsm.incident.triage end-to-end:
                                normalize -> classify -> suggest_priority ->
                                DMN(priority) -> DMN(ownership) -> DMN(routing) ->
                                incident.update (apply + transition triaged) ->
                                draft_response (PROPOSED) -> event.emit(routed)

All of the above happens in a single DB transaction. The response carries
both the SignalResponse and a triage summary so demo UIs can render the
routing decision immediately.

Set TRIAGE_AUTO=false in env to skip step 3 (useful for dev / debugging
when you want to inspect the raw open case before triage runs).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from openlegal.core.config import settings
from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal, SignalStatus
from openlegal.schemas.intake import (
    IntakeResponse,
    TriageResultResponse,
    TriageStepSummary,
)
from openlegal.schemas.signal import SignalCreate, SignalResponse
from openlegal.models.uapf_session import UAPFSessionState
from openlegal.services.incident import open_case_from_signal
from openlegal.services.triage import build_triage_result_from_case, run_triage_inline
from openlegal.uapf.bridge import start_uapf_run


router = APIRouter()


@router.post(
    "/",
    response_model=IntakeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Receive a signal from an adapter (and triage it)",
)
async def post_signal(
    body: SignalCreate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> IntakeResponse:
    """Create a Signal, open a Case, run inline triage."""
    return await _process_intake_payload(body, session=session, org=org)


async def _process_intake_payload(
    body: SignalCreate,
    *,
    session: AsyncSession,
    org: Organization,
) -> IntakeResponse:
    """Inner helper: create signal+case, run triage, sign VCs.

    Extracted so non-HTTP entrypoints (the UAPF demo console, batch
    backfills, etc.) can run the same pipeline without re-implementing it.
    Identical observable behavior to the route handler.
    """
    received_at = body.received_at or datetime.now(timezone.utc)

    signal = Signal(
        org_id=org.id,
        connection_id=body.connection_id,
        source=body.source,
        external_id=body.external_id,
        raw_payload=body.raw_payload,
        normalized_payload=body.normalized_payload,
        received_at=received_at,
        dedupe_hash=body.dedupe_hash,
        status=SignalStatus.RECEIVED,
    )
    session.add(signal)
    await session.flush()

    title = _derive_title(body)
    description = _derive_description(body)
    case = await open_case_from_signal(
        session, org=org, signal=signal,
        title=title, description=description,
        actor_label=f"intake/{body.source.value}",
    )
    await session.flush()

    triage_response: TriageResultResponse | None = None
    if settings.TRIAGE_AUTO:
        triage = None
        uapf_session = None

        # Commit signal+case BEFORE engine call so engine's out-of-band capability
        # callbacks (in their own sessions) can see the freshly-created rows.
        # Without this, every callback fails with "signal X not found in org" /
        # "case Y not found in org" due to read-committed isolation.
        if settings.UAPF_ENABLED:
            await session.commit()

        # Try UAPF engine first if enabled. Falls back to inline on any failure.
        if settings.UAPF_ENABLED:
            uapf_session = await start_uapf_run(
                session, org,
                package_id="lv.itsm.incident.triage",
                process_id="incident-triage",  # BPMN artifact id from manifest, not internal <process id>
                input_payload={
                    "signal_id": str(signal.id),
                    "case_id": str(case.id),
                },
                case=case, signal=signal,
                trace_id=f"triage-{case.case_number}",
            )

        engine_drove = (
            uapf_session is not None
            and uapf_session.state == UAPFSessionState.COMPLETED
        )

        if engine_drove:
            # Engine handled the process via host-handler callbacks in OTHER
            # sessions (now committed). Expire local case-object cache so we
            # re-read mutated scalar columns + relationships from DB.
            await session.refresh(case)

        # Engine-completed doesn't yet guarantee the case was actually mutated:
        # the v1.0.0 BPMN lacks dataObject/dataAssociation wiring, so downstream
        # tasks (incident.update etc.) receive empty inputs and case state stays
        # null. Detect this and fall through to inline so the demo keeps working.
        # When BPMN data flow is wired in Phase 2, this fallback will be dead code.
        if (engine_drove and case.priority is not None
                and case.assigned_group_id is not None):
            triage = await build_triage_result_from_case(session, case)
        else:
            triage = await run_triage_inline(
                session, org, signal=signal, case=case,
            )
            await session.flush()

        # Post-triage VC signing: anchor the lifecycle events (Opened,
        # Classified, Prioritized, Routed) into VeriDocs Register via the
        # SDK. Best-effort — if the SDK is down the case still completes.
        try:
            from openlegal.services.vc_signing import sign_triage_events
            await sign_triage_events(session, org, case)
        except Exception as exc:
            logger.warning(
                "VC signing pass failed for %s: %s",
                case.case_number, exc, exc_info=False,
            )

        triage_response = TriageResultResponse(
            case_id=triage.case_id,
            case_number=triage.case_number,
            classification=triage.classification,
            priority=triage.priority,
            ownership=triage.ownership,
            group_slug=triage.group_slug,
            group_id=triage.group_id,
            steps=[TriageStepSummary(**s) for s in triage.steps],
        )

    await session.refresh(signal)
    return IntakeResponse(
        signal=SignalResponse.model_validate(signal),
        triage=triage_response,
    )


def _derive_title(body: SignalCreate) -> str:
    payload = body.normalized_payload or body.raw_payload or {}
    for key in ("title", "subject", "summary", "description", "message"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:512]
    return f"[{body.source.value}] {body.external_id or 'signal'}"


def _derive_description(body: SignalCreate) -> str | None:
    payload = body.normalized_payload or body.raw_payload or {}
    v = payload.get("body") or payload.get("description")
    return v if isinstance(v, str) else None
