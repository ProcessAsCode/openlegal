"""Agreement-monitoring run + Jira Cloud connection management (sandbox POC).

Endpoints (mounted at /api/uapf):
  GET  /connections            list this org's connections (token redacted)
  POST /connections/jira       create/update the org's jira_cloud connection
  POST /connections/jira/test  verify credentials against /rest/api/3/myself
  POST /run-agreement          run lv.proc.it_agreement.monitoring end-to-end:
                               load -> scan -> classify -> per obligation
                               (auto -> create_due_dated | gated -> penalty +
                               create_proposed) via the host UAPF capabilities,
                               creating real Jira issues through the connection.
"""
from __future__ import annotations

import base64
import uuid

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.connection import Connection, ConnectionKind, ConnectionStatus
from openlegal.models.organization import Organization
from openlegal.uapf.dispatcher import dispatch

router = APIRouter()
PKG = "lv.proc.it_agreement.monitoring"


class JiraConnIn(BaseModel):
    name: str = "Sandbox Jira Cloud"
    base_url: str
    project_key: str
    email: str
    api_token: str | None = None


def _redact(conn: Connection) -> dict:
    cfg = dict(conn.config or {})
    has_token = bool(cfg.pop("api_token", None))
    return {"id": str(conn.id), "kind": conn.kind.value, "name": conn.name,
            "config": cfg, "has_token": has_token, "is_enabled": conn.is_enabled,
            "status": conn.status.value, "last_error": conn.last_error}


async def _jira_conn(session, org):
    return (await session.execute(select(Connection).where(
        Connection.org_id == org.id,
        Connection.kind == ConnectionKind.JIRA_CLOUD,
        Connection.is_enabled.is_(True)))).scalars().first()


@router.get("/connections")
async def list_connections(org=Depends(get_current_org),
                           session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Connection).where(Connection.org_id == org.id))).scalars().all()
    return {"connections": [_redact(c) for c in rows]}


@router.post("/connections/jira")
async def upsert_jira(body: JiraConnIn, org=Depends(get_current_org),
                      session: AsyncSession = Depends(get_session)):
    existing = (await session.execute(select(Connection).where(
        Connection.org_id == org.id,
        Connection.kind == ConnectionKind.JIRA_CLOUD))).scalars().first()
    cfg = {"base_url": body.base_url, "project_key": body.project_key, "email": body.email}
    if existing:
        merged = dict(existing.config or {})
        merged.update(cfg)
        if body.api_token:
            merged["api_token"] = body.api_token
        existing.config = merged
        existing.name = body.name
        existing.is_enabled = True
        conn = existing
    else:
        if body.api_token:
            cfg["api_token"] = body.api_token
        conn = Connection(org_id=org.id, kind=ConnectionKind.JIRA_CLOUD,
                          name=body.name, config=cfg,
                          status=ConnectionStatus.ACTIVE, is_enabled=True)
        session.add(conn)
    await session.flush()
    await session.commit()
    return _redact(conn)


@router.post("/connections/jira/test")
async def test_jira(org=Depends(get_current_org),
                    session: AsyncSession = Depends(get_session)):
    conn = await _jira_conn(session, org)
    if conn is None:
        return {"ok": False, "reason": "no enabled jira_cloud connection"}
    cfg = conn.config or {}
    base = (cfg.get("base_url") or "").rstrip("/")
    email = cfg.get("email")
    token = cfg.get("api_token")
    if not (base and email and token):
        return {"ok": False, "reason": "incomplete (need base_url, email, api_token)"}
    auth = "Basic " + base64.b64encode(("%s:%s" % (email, token)).encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get("%s/rest/api/3/myself" % base,
                            headers={"Authorization": auth, "Accept": "application/json"})
        ok = r.status_code < 300
        conn.status = ConnectionStatus.ACTIVE if ok else ConnectionStatus.ERROR
        conn.last_error = None if ok else ("jira %s: %s" % (r.status_code, r.text[:160]))
        await session.commit()
        return {"ok": ok, "status": r.status_code,
                "account": (r.json().get("emailAddress") if ok else None),
                "reason": None if ok else conn.last_error}
    except Exception as e:
        return {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}


@router.post("/run-agreement")
async def run_agreement(org=Depends(get_current_org),
                        session: AsyncSession = Depends(get_session)):
    ctx = {"uapf_package_id": PKG, "trace_id": "run-" + uuid.uuid4().hex[:8],
           "execution_id": None}
    loaded = await dispatch(session, org, capability_name="agreement.load",
                            inputs={}, context=ctx)
    if loaded["status"] != "success":
        return {"ok": False, "stage": "agreement.load", "error": loaded.get("error")}
    agreement = loaded["output"]["agreement"]
    scanned = await dispatch(session, org, capability_name="obligation.scan",
                             inputs={"agreement": agreement}, context=ctx)
    classified = await dispatch(session, org, capability_name="ai.classify_clause",
                                inputs={"agreement": agreement}, context=ctx)
    budget = agreement.get("budget") or {}
    if isinstance(budget, list):
        budget = next((b for b in budget if isinstance(b, dict)), {})
    price = (budget.get("amount") or budget.get("contract_price") or 0) if isinstance(budget, dict) else 0
    sl = agreement.get("service_levels") or {}
    if isinstance(sl, list):
        sl = next((x for x in sl if isinstance(x, dict)), {})
    per_day = (sl.get("penalty_per_day_pct") if isinstance(sl, dict) else None) or 0.1
    cap_pct = (sl.get("penalty_cap_pct") if isinstance(sl, dict) else None) or 10
    results = []
    for st in scanned["output"]["obligation_states"]:
        mode = st.get("mode", "auto")
        penalty = None
        if mode == "gated":
            pen = await dispatch(session, org, capability_name="penalty.accrue",
                                 inputs={"overdue_amount": price, "days_late": 1,
                                         "per_day_pct": per_day, "cap_pct": cap_pct,
                                         "contract_price": price}, context=ctx)
            penalty = pen.get("output")
            action = "create_proposed"
        else:
            action = "create_due_dated"
        emit = await dispatch(session, org, capability_name="jira.create_issue",
                              inputs={"obligation_id": st["obligation_id"],
                                      "jira_issue_type": st.get("jira_issue_type", "Task"),
                                      "action": action, "mode": mode,
                                      "due_date": st.get("due_date", "")}, context=ctx)
        results.append({"obligation_id": st["obligation_id"],
                        "type": st["obligation_type"], "state": st["state"],
                        "mode": mode, "action": action, "penalty": penalty,
                        "jira": emit.get("output")})
    await session.commit()
    created = sum(1 for r in results if (r["jira"] or {}).get("created"))
    jconn = await _jira_conn(session, org)
    jira_base = ((jconn.config or {}).get("base_url") if jconn else None)
    return {"ok": True, "agreement_id": agreement.get("id"),
            "agreement_title": agreement.get("title"), "package": PKG,
            "obligations": len(results), "jira_created": created,
            "jira_base_url": jira_base,
            "classifications": (classified.get("output") or {}).get("count"),
            "results": results}


@router.get("/orgs")
async def list_orgs(session: AsyncSession = Depends(get_session)):
    """List all organizations (slug + name) for the header org switcher."""
    rows = (await session.execute(
        select(Organization).order_by(Organization.slug))).scalars().all()
    return {"orgs": [{"slug": o.slug, "name": o.name} for o in rows]}


@router.get("/agreement")
async def get_agreement(org=Depends(get_current_org),
                        session: AsyncSession = Depends(get_session)):
    """Load and return the UAS agreement the package monitors (for display)."""
    ctx = {"uapf_package_id": PKG, "trace_id": "view", "execution_id": None}
    loaded = await dispatch(session, org, capability_name="agreement.load",
                            inputs={}, context=ctx)
    if loaded["status"] != "success":
        return {"ok": False, "error": loaded.get("error")}
    return {"ok": True, "package": PKG, "agreement": loaded["output"]["agreement"]}
