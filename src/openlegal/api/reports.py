"""Lightweight org-level metrics for the Reports page.

Real reporting (SLA compliance over time, MTTR trends, AI accuracy) is Phase 1 work.
For the POC this endpoint returns the basic counts and breakdowns the Reports
landing dashboard renders as tiles + small bar charts.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.case import Case
from openlegal.models.case_event import CaseEvent
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal
from openlegal.models.vc_reference import VCReference

router = APIRouter()


@router.get("/summary")
async def reports_summary(
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Total cases
    total_cases = (await session.execute(
        select(func.count(Case.id)).where(Case.org_id == org.id)
    )).scalar_one()

    # By status
    status_rows = (await session.execute(
        select(Case.status, func.count(Case.id))
            .where(Case.org_id == org.id)
            .group_by(Case.status)
    )).all()
    by_status = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in status_rows}

    # By priority (NULL bucketed as "—")
    pri_rows = (await session.execute(
        select(Case.priority, func.count(Case.id))
            .where(Case.org_id == org.id)
            .group_by(Case.priority)
    )).all()
    by_priority: dict[str, int] = {}
    for row in pri_rows:
        key = (row[0].value if hasattr(row[0], "value") else str(row[0])) if row[0] is not None else "—"
        by_priority[key] = row[1]

    # By source
    src_rows = (await session.execute(
        select(Signal.source, func.count(Signal.id))
            .where(Signal.org_id == org.id)
            .group_by(Signal.source)
    )).all()
    by_source = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in src_rows}

    # Signed VCs total + by type
    total_vcs = (await session.execute(
        select(func.count(VCReference.id)).where(VCReference.org_id == org.id)
    )).scalar_one()
    vc_rows = (await session.execute(
        select(VCReference.vc_type, func.count(VCReference.id))
            .where(VCReference.org_id == org.id)
            .group_by(VCReference.vc_type)
    )).all()
    vcs_by_type = {row[0].value if hasattr(row[0], "value") else str(row[0]): row[1] for row in vc_rows}

    # Total events (audit chain depth)
    total_events = (await session.execute(
        select(func.count(CaseEvent.id))
            .join(Case, Case.id == CaseEvent.case_id)
            .where(Case.org_id == org.id)
    )).scalar_one()

    # Triaged / resolved /closed totals for MTTR-ish display
    triaged = sum(by_status.get(k, 0) for k in ("triaged", "in_progress", "waiting_customer", "waiting_third_party", "resolved", "closed"))
    resolved = sum(by_status.get(k, 0) for k in ("resolved", "closed"))

    return {
        "totals": {
            "cases": total_cases,
            "events": total_events,
            "signed_vcs": total_vcs,
            "triaged": triaged,
            "resolved": resolved,
        },
        "by_status": by_status,
        "by_priority": by_priority,
        "by_source": by_source,
        "vcs_by_type": vcs_by_type,
    }
