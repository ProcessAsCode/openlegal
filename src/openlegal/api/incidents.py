"""Incidents router — case list, detail, manual create, transition, timeline."""

from __future__ import annotations

import uuid

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.case import Case, CaseStatus
from openlegal.models.case_event import CaseEvent
from openlegal.models.organization import Organization
from openlegal.schemas.case import (
    CaseCreate,
    CaseDetail,
    CaseSummary,
    CaseTransition,
)
from openlegal.schemas.case_event import CaseEventResponse
from openlegal.services.incident import (
    IllegalTransitionError,
    get_case_by_id,
    open_case_manual,
    transition_case,
)


router = APIRouter()


@router.get(
    "/",
    response_model=list[CaseSummary],
    summary="List incidents (most-recently-updated first)",
)
async def list_incidents(
    status_filter: list[CaseStatus] | None = Query(
        default=None, alias="status",
        description="Filter to one or more statuses",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> list[CaseSummary]:
    stmt = select(Case).where(Case.org_id == org.id)
    if status_filter:
        stmt = stmt.where(Case.status.in_(status_filter))
    stmt = stmt.order_by(desc(Case.updated_at)).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [CaseSummary.model_validate(r) for r in rows]


@router.post(
    "/",
    response_model=CaseDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Manually open a case (no originating signal)",
)
async def create_incident(
    body: CaseCreate,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> CaseDetail:
    case = await open_case_manual(
        session,
        org=org,
        title=body.title,
        description=body.description,
        priority=body.priority.value if body.priority else None,
        classification_id=body.classification_id,
        service_tier_id=body.service_tier_id,
        actor_label="api/manual-create",
    )
    await session.flush()
    await session.refresh(case)
    return CaseDetail.model_validate(case)


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Get one incident by id",
)
async def get_incident(
    case_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> CaseDetail:
    case = await get_case_by_id(session, org.id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    return CaseDetail.model_validate(case)


@router.post(
    "/{case_id}/transition",
    response_model=CaseDetail,
    summary="Transition an incident to a new status",
)
async def transition_incident(
    case_id: uuid.UUID,
    body: CaseTransition,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> CaseDetail:
    case = await get_case_by_id(session, org.id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    try:
        await transition_case(
            session,
            case,
            to_status=body.to_status,
            reason=body.reason,
            actor_label="api/transition",
        )
    except IllegalTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await session.flush()
    await session.refresh(case)
    return CaseDetail.model_validate(case)


@router.get(
    "/{case_id}/events",
    response_model=list[CaseEventResponse],
    summary="Read the append-only timeline for an incident",
)
async def list_incident_events(
    case_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> list[CaseEventResponse]:
    case = await get_case_by_id(session, org.id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    from sqlalchemy.orm import selectinload
    stmt = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .options(selectinload(CaseEvent.vc_reference))
        .order_by(CaseEvent.created_at)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    responses = []
    for r in rows:
        d = CaseEventResponse.model_validate(r).model_dump()
        if r.vc_reference is not None:
            d["vc"] = {
                "vc_id": r.vc_reference.vc_id,
                "vc_type": r.vc_reference.vc_type.value if hasattr(r.vc_reference.vc_type, "value") else str(r.vc_reference.vc_type),
                "issuer_did": r.vc_reference.issuer_did,
                "subject_did": r.vc_reference.subject_did,
                "vc_hash": r.vc_reference.vc_hash,
            }
        responses.append(d)
    return responses



@router.get("/events/audit", response_model=None)
async def list_org_events(
    limit: int = Query(default=100, ge=1, le=500),
    since_hours: int = Query(default=72, ge=1, le=720),
    type_filter: str | None = Query(default=None, alias="type"),
    signed_only: bool = Query(default=False),
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Org-wide cross-case audit feed. Each row carries case_number + the VC info if present."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import selectinload
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    stmt = (
        select(CaseEvent)
        .join(Case, Case.id == CaseEvent.case_id)
        .where(Case.org_id == org.id, CaseEvent.created_at >= cutoff)
        .options(
            selectinload(CaseEvent.case),
            selectinload(CaseEvent.vc_reference),
        )
        .order_by(CaseEvent.created_at.desc())
        .limit(limit)
    )
    if type_filter:
        stmt = stmt.where(CaseEvent.type == type_filter)
    if signed_only:
        stmt = stmt.where(CaseEvent.vc_reference_id.is_not(None))
    rows = (await session.execute(stmt)).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": str(r.id),
            "case_id": str(r.case_id),
            "case_number": r.case.case_number if r.case else None,
            "type": r.type.value if hasattr(r.type, "value") else str(r.type),
            "actor_type": r.actor_type.value if hasattr(r.actor_type, "value") else str(r.actor_type),
            "actor_label": r.actor_label,
            "trace_id": r.trace_id,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "vc": {
                "vc_id": r.vc_reference.vc_id,
                "vc_type": r.vc_reference.vc_type.value if hasattr(r.vc_reference.vc_type, "value") else str(r.vc_reference.vc_type),
                "issuer_did": r.vc_reference.issuer_did,
                "subject_did": r.vc_reference.subject_did,
                "vc_hash": r.vc_reference.vc_hash,
            } if r.vc_reference else None,
        })
    return out



@router.get("/vc/{vc_id_path:path}/verify", response_model=None)
async def vc_verify(
    vc_id_path: str,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Verify a VC anchored in the VeriDocs Register.

    Looks the VC up by id in vc_references (org-scoped), pulls the sdk_response
    payload that holds the credentialSubject + proof, and asks the SDK's
    /api/vc/verify endpoint to re-verify the proof. Returns the verifier
    response (verified true/false) so the SPA can render an inline check
    next to the shield popover."""
    from openlegal.models.vc_reference import VCReference
    from openlegal import sdk_client

    stmt = select(VCReference).where(
        VCReference.org_id == org.id,
        VCReference.vc_id == vc_id_path,
    )
    vc_ref = (await session.execute(stmt)).scalar_one_or_none()
    if not vc_ref:
        raise HTTPException(status_code=404, detail=f"VC {vc_id_path} not in this org")

    raw = vc_ref.sdk_response or {}
    credential = (
        raw.get("vc")
        or raw.get("credential")
        or raw.get("verifiableCredential")
        or raw.get("document", {}).get("vc")
        or raw.get("documentVc")
    )
    if not credential:
        return {
            "vc_id": vc_ref.vc_id,
            "verified": None,
            "reason": "VC payload not retained in sdk_response — re-issue to enable verify",
            "issuer_did": vc_ref.issuer_did,
        }

    verify_result = await sdk_client.verify_vc(credential)
    return {
        "vc_id": vc_ref.vc_id,
        "issuer_did": vc_ref.issuer_did,
        "vc_type": vc_ref.vc_type.value if hasattr(vc_ref.vc_type, "value") else str(vc_ref.vc_type),
        "verified": bool(verify_result and verify_result.get("verified")),
        "raw": verify_result,
    }
