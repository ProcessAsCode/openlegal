"""Governance scheduling API (legal pilot, v0.1).

GET  /api/legal/schedule/bodies           - cadence rules in effect
GET  /api/legal/schedule/compute          - chain plan for explicit inputs
GET  /api/legal/schedule/contracts        - plans for every sample UAS contract
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.connection import Connection, ConnectionKind, ConnectionStatus
from openlegal.models.legal_agreement import AgreementStatus, LegalAgreement
from openlegal.uapf.dispatcher import dispatch
from openlegal.uapf.handlers.legal import read_alerts

from openlegal.services.governance import required_approvals as _required_approvals_svc
from openlegal.services.scheduler import GovernanceScheduler, plan_to_dict

router = APIRouter()
PKG_DIR = Path("/app/uapf-packages/lv.example.legal.governance_monitoring")


def _scheduler() -> GovernanceScheduler:
    try:
        return GovernanceScheduler.from_package(PKG_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"governance calendar rules not found: {exc}")


def _required_approvals(value_eur: float, material: bool) -> list[str]:
    return _required_approvals_svc(value_eur, material)


@router.get("/schedule/bodies")
async def bodies():
    return _scheduler().bodies


@router.get("/schedule/sittings")
async def sittings(start: date | None = Query(None),
                   weeks: int = Query(10, ge=1, le=52)):
    """Upcoming governance calendar: sittings per recurring body with
    submission cutoffs, plus lead-time/on-demand body metadata."""
    sched = _scheduler()
    today = start or date.today()
    horizon = weeks * 7
    bodies_meta, events = [], []
    for key, cfg in sched.bodies.items():
        kind = cfg.get("kind")
        meta = {"body": key, "label": cfg.get("label", key), "kind": kind,
                "prerequisite": cfg.get("prerequisite")}
        if kind == "recurring":
            meta["cadence"] = cfg.get("cadence")
            meta["pattern"] = cfg.get("weekday") or cfg.get("rule")
            cutoff_wd = int(cfg.get("submission_cutoff_working_days", 0))
            meta["submission_cutoff_working_days"] = cutoff_wd
            from openlegal.services.scheduler import add_working_days
            for s in sched.sittings(key, after=today, horizon_days=horizon):
                events.append({"body": key, "label": meta["label"],
                               "date": s.isoformat(),
                               "submit_by": add_working_days(s, -cutoff_wd).isoformat()})
        elif kind == "lead_time":
            meta["lead_working_days"] = cfg.get("lead_working_days")
        elif kind == "on_demand":
            meta["lead_calendar_days"] = cfg.get("lead_calendar_days")
        bodies_meta.append(meta)
    events.sort(key=lambda e: (e["date"], e["body"]))
    return {"as_of": today.isoformat(), "weeks": weeks,
            "bodies": bodies_meta, "sittings": events}


@router.get("/schedule/compute")
async def compute(deadline: date = Query(...),
                  value_eur: float = Query(...),
                  material: bool = Query(False),
                  start: date | None = Query(None)):
    approvals = _required_approvals(value_eur, material)
    plan = _scheduler().compute_chain(deadline, approvals, start=start)
    return {"value_eur": value_eur, "material": material, **plan_to_dict(plan)}


@router.get("/schedule/contracts")
async def contracts(org=Depends(get_current_org),
                    session: AsyncSession = Depends(get_session),
                    start: date | None = Query(None)):
    """Chain plans for every agreement in the org's Agreement Register."""
    sched = _scheduler()
    today = start or date.today()
    out = []
    for row in await _register_rows(session, org):
        uas = row.uas
        gov = uas.get("governance", {})
        pend = gov.get("pending_amendment")
        value = pend["new_value"] if pend else uas["commercials"]["contract_value"]
        deadline_s = pend["deadline"] if pend else uas["lifecycle"]["expires"]
        approvals = _required_approvals(float(value), bool(gov.get("material", False)))
        plan = sched.compute_chain(date.fromisoformat(deadline_s), approvals, start=today)
        out.append({"agreement_id": row.agreement_id, "title": row.title,
                    "value_eur": value, "deadline": deadline_s,
                    "plan": plan_to_dict(plan)})
    return {"as_of": today.isoformat(), "contracts": out}


# --- governance run loop (drives capabilities through the dispatcher) --------

_PKG_CTX = {"uapf_package_id": "lv.example.legal.governance_monitoring"}


@router.get("/alerts")
async def alerts(org=Depends(get_current_org), limit: int = 100):
    return {"alerts": read_alerts(org.slug, limit)}


@router.post("/run-governance")
async def run_governance(org=Depends(get_current_org),
                         session: AsyncSession = Depends(get_session),
                         start: date | None = Query(None)):
    """One governance-monitoring run over every contract in the registry.

    Pipeline per contract: docus.read -> sap.read_actuals -> evaluate
    obligations -> governance.evaluate + schedule.compute_chain for approval
    obligations -> notify.alert per finding. All steps go through the UAPF
    dispatcher so each capability invocation is recorded.
    """
    today = start or date.today()
    import uuid as _uuid
    run_id = str(_uuid.uuid4())
    # NOTE: dispatch persistence requires an execution row FK'd to a case
    # (ITSM coupling) — governance runs use non-persistent dispatch in v0.1.
    ctx = dict(_PKG_CTX)
    rows = await _register_rows(session, org)
    report = {"run_at": datetime_now(), "org": org.slug, "as_of": today.isoformat(),
              "run_id": run_id,
              "contracts": [], "alerts_created": 0}

    for row in rows:
        uas = row.uas
        sap_id = uas.get("provenance", {}).get("sap_contract_id")
        actuals = (await dispatch(session, org, capability_name="sap.read_actuals",
                                  inputs={"sap_contract_id": sap_id}, context=ctx))["output"]
        findings = _evaluate_contract(uas, actuals, today)

        for f in findings:
            if f["obligation_type"] == "governance_approval":
                gov = uas.get("governance", {})
                pend = gov.get("pending_amendment")
                value = pend["new_value"] if pend else uas["commercials"]["contract_value"]
                deadline = pend["deadline"] if pend else uas["lifecycle"]["expires"]
                chain = (await dispatch(session, org, capability_name="schedule.compute_chain",
                                       inputs={"deadline": deadline, "value_eur": value,
                                               "material": gov.get("material", False),
                                               "start": today.isoformat()},
                                       context=ctx))["output"]
                f["schedule"] = chain
                if not chain["feasible"]:
                    f["state"] = "chain_infeasible"
                    f["action"] = "escalate_infeasible_chain"
                    f["severity"] = "critical"
            res = (await dispatch(session, org, capability_name="notify.alert",
                                 inputs={"severity": f.get("severity", "warning"),
                                         "contract": uas["id"], "obligation": f["obligation"],
                                         "state": f["state"], "action": f["action"],
                                         "message": f["message"],
                                         "detail": f.get("schedule")},
                                 context=ctx))["output"]
            f["alert_id"] = res.get("alert_id")
            report["alerts_created"] += 1

        report["contracts"].append({"contract": uas["id"], "title": uas["title"],
                                    "docus_id": row.source_docus_id, "findings": findings})
    return report


def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _evaluate_contract(uas: dict, actuals: dict, today: date) -> list[dict]:
    """Obligation rules -> findings (mirrors dmn/obligation_action.json)."""
    out = []
    life = uas.get("lifecycle", {})
    expires = date.fromisoformat(life["expires"]) if life.get("expires") else None
    gov = uas.get("governance", {})

    for ob in uas.get("obligations", []):
        t, oid = ob.get("type"), ob.get("id")
        if t == "renewal" and expires:
            window = expires.toordinal() - int(ob.get("value") or 0)
            if date.fromordinal(window) <= today <= expires:
                out.append({"obligation": oid, "obligation_type": t, "state": "window_open",
                            "action": "create_renewal_task", "severity": "warning",
                            "message": f"Renewal window open: contract expires {expires}, "
                                       f"{(expires - today).days} days left to decide."})
        elif t == "payment_control" and expires and actuals.get("found"):
            late = [p for p in actuals.get("payments", [])
                    if date.fromisoformat(p["date"]) > expires]
            if late:
                out.append({"obligation": oid, "obligation_type": t, "state": "violation",
                            "action": "alert_payment_after_expiry", "severity": "critical",
                            "message": f"{len(late)} payment(s) dated after contract end {expires}."})
        elif t == "budget_threshold" and actuals.get("found"):
            limit = actuals.get("approved_limit_eur") or 0
            spend = actuals.get("actual_spend_eur") or 0
            pct = round(spend / limit * 100, 1) if limit else 0
            crossed = [th for th in (ob.get("value") or []) if pct >= th]
            if crossed:
                out.append({"obligation": oid, "obligation_type": t, "state": "threshold_crossed",
                            "action": "alert_limit_threshold", "severity": "warning",
                            "message": f"Actual spend at {pct}% of approved limit "
                                       f"(EUR {spend:,.0f} / {limit:,.0f}); thresholds crossed: {crossed}."})
        elif t == "governance_approval":
            missing = gov.get("approvals_missing") or []
            pend = gov.get("pending_amendment")
            if oid == "ob.chain_completeness" and missing:
                out.append({"obligation": oid, "obligation_type": t, "state": "approvals_missing",
                            "action": "propose_agenda_items_with_schedule", "severity": "warning",
                            "message": f"Required approvals missing on file: {', '.join(missing)}."})
            elif oid == "ob.amendment_approval" and pend:
                out.append({"obligation": oid, "obligation_type": t, "state": "approvals_missing",
                            "action": "propose_agenda_items_with_schedule", "severity": "warning",
                            "message": f"Pending amendment to EUR {pend['new_value']:,} "
                                       f"(deadline {pend['deadline']}) requires the approval chain."})
    return out


# --- Agreement Register -------------------------------------------------------


async def _register_rows(session, org):
    stmt = (select(LegalAgreement)
            .where(LegalAgreement.org_id == org.id)
            .order_by(LegalAgreement.agreement_id))
    return list((await session.execute(stmt)).scalars())


def _summary(row: LegalAgreement) -> dict:
    uas = row.uas or {}
    return {
        "agreement_id": row.agreement_id,
        "title": row.title,
        "status": row.status,
        "value_eur": (uas.get("commercials") or {}).get("contract_value"),
        "expires": (uas.get("lifecycle") or {}).get("expires"),
        "source_docus_id": row.source_docus_id,
        "source_sap_id": row.source_sap_id,
        "obligations": len(uas.get("obligations") or []),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/agreements")
async def agreements_list(org=Depends(get_current_org),
                          session: AsyncSession = Depends(get_session)):
    return {"agreements": [_summary(r) for r in await _register_rows(session, org)]}


@router.get("/agreements/{agreement_id}")
async def agreement_detail(agreement_id: str, org=Depends(get_current_org),
                           session: AsyncSession = Depends(get_session)):
    stmt = select(LegalAgreement).where(LegalAgreement.org_id == org.id,
                                        LegalAgreement.agreement_id == agreement_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"agreement {agreement_id} not in register")
    return {**_summary(row), "uas": row.uas}


@router.post("/agreements/import")
async def agreement_import(uas: dict, org=Depends(get_current_org),
                           session: AsyncSession = Depends(get_session)):
    """Upsert one UAS document into the org's Agreement Register."""
    aid = uas.get("id")
    if not aid:
        raise HTTPException(422, "UAS document must carry an 'id'")
    stmt = select(LegalAgreement).where(LegalAgreement.org_id == org.id,
                                        LegalAgreement.agreement_id == aid)
    row = (await session.execute(stmt)).scalar_one_or_none()
    prov = uas.get("provenance") or {}
    if row is None:
        row = LegalAgreement(org_id=org.id, agreement_id=aid)
        session.add(row)
        created = True
    else:
        created = False
    row.title = uas.get("title") or aid
    row.status = AgreementStatus(uas.get("status", "active")) if uas.get("status") in [s.value for s in AgreementStatus] else AgreementStatus.ACTIVE
    row.source_docus_id = prov.get("docus_id") or prov.get("docus_record")
    row.source_sap_id = prov.get("sap_contract_id")
    row.uas = uas
    await session.commit()
    return {"imported": aid, "created": created}


# --- Source connectors (DOCUS registry / SAP actuals) -------------------------

_LEGAL_KINDS = {
    "docus_registry": ConnectionKind.DOCUS_REGISTRY,
    "sap_actuals": ConnectionKind.SAP_ACTUALS,
    "ms_purview": ConnectionKind.MS_PURVIEW,
}
_KIND_CAPABILITY = {
    "docus_registry": "docus.read",
    "sap_actuals": "sap.read_actuals",
    "ms_purview": "mip.read_protected",
}


def _legal_kind(kind: str) -> ConnectionKind:
    if kind not in _LEGAL_KINDS:
        raise HTTPException(404, f"unknown legal connector kind: {kind}")
    return _LEGAL_KINDS[kind]


def _conn_info(c: Connection) -> dict:
    return {"id": str(c.id), "kind": c.kind, "name": c.name, "config": c.config or {},
            "is_enabled": c.is_enabled, "status": c.status}


@router.get("/connections")
async def legal_connections(org=Depends(get_current_org),
                            session: AsyncSession = Depends(get_session)):
    stmt = select(Connection).where(Connection.org_id == org.id,
                                    Connection.kind.in_(list(_LEGAL_KINDS.values())))
    return {"connections": [_conn_info(c) for c in (await session.execute(stmt)).scalars()]}


@router.put("/connections/{kind}")
async def legal_connection_save(kind: str, payload: dict,
                                org=Depends(get_current_org),
                                session: AsyncSession = Depends(get_session)):
    k = _legal_kind(kind)
    stmt = select(Connection).where(Connection.org_id == org.id, Connection.kind == k)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = Connection(org_id=org.id, kind=k,
                         name=payload.get("name") or kind, config={},
                         status=ConnectionStatus.ACTIVE)
        session.add(row)
    if payload.get("name"):
        row.name = payload["name"]
    cfg = dict(row.config or {})
    for key in ("mode", "base_url", "export_path", "note"):
        if key in payload:
            cfg[key] = payload[key]
    cfg.setdefault("mode", "mock")
    row.config = cfg
    row.is_enabled = bool(payload.get("is_enabled", True))
    await session.commit()
    return _conn_info(row)


@router.post("/connections/{kind}/test")
async def legal_connection_test(kind: str, org=Depends(get_current_org),
                                session: AsyncSession = Depends(get_session)):
    """Exercise the adapter behind this connector (mock in v0.1)."""
    _legal_kind(kind)
    res = await dispatch(session, org, capability_name=_KIND_CAPABILITY[kind],
                         inputs={}, context=dict(_PKG_CTX))
    out = res.get("output") or {}
    ok = res.get("status") == "success"
    return {"ok": ok, "adapter": out.get("adapter", "unknown"),
            "records": out.get("count"), "error": res.get("error")}
