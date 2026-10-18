"""Inbound Jira Cloud webhook receiver (sandbox POC) — closes the loop.

Mounted at /api/uapf:
  POST /jira/webhook?org=<slug>&token=<secret>   receive a Jira issue event
  GET  /jira/webhook/events                       recent inbound events (X-Org-Slug)

This path is exempt from the demo Basic-Auth at the reverse proxy; authenticity
is enforced here via a shared secret (OPENLEGAL_WEBHOOK_SECRET), supplied as the
`token` query param or `X-Webhook-Token` header and compared in constant time.
When a gated ("proposed") obligation ticket is moved to an approval/done status
in Jira, OpenLegal records the event and posts a confirmation comment back on the
issue — Jira-originated triggers driving OpenLegal, the reverse of the outbound
create/transition path.
"""
from __future__ import annotations

import base64
import hmac

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.core.config import settings
from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.connection import Connection, ConnectionKind
from openlegal.models.organization import Organization

router = APIRouter()

APPROVAL_STATES = {"approved", "accepted", "done", "closed", "resolved", "completed"}

_DDL = (
    "CREATE TABLE IF NOT EXISTS jira_webhook_events ("
    " id BIGSERIAL PRIMARY KEY, org_id TEXT, issue_key TEXT, event TEXT,"
    " status TEXT, is_approval BOOLEAN DEFAULT FALSE, acted TEXT,"
    " received_at TIMESTAMPTZ DEFAULT now(), raw_summary TEXT)"
)


def _auth_header(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(("%s:%s" % (email, token)).encode()).decode()


async def _jira_conn(session, org):
    return (await session.execute(select(Connection).where(
        Connection.org_id == org.id,
        Connection.kind == ConnectionKind.JIRA_CLOUD,
        Connection.is_enabled.is_(True)))).scalars().first()


async def _post_comment(session, org, key: str, body_text: str) -> dict:
    conn = await _jira_conn(session, org)
    if conn is None:
        return {"ok": False, "reason": "no enabled jira_cloud connection"}
    cfg = conn.config or {}
    base = (cfg.get("base_url") or "").rstrip("/")
    email = cfg.get("email")
    token = cfg.get("api_token")
    if not (base and email and token):
        return {"ok": False, "reason": "jira connection incomplete"}
    adf = {"body": {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": body_text}]}]}}
    headers = {"Authorization": _auth_header(email, token),
               "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post("%s/rest/api/3/issue/%s/comment" % (base, key),
                             json=adf, headers=headers)
        return {"ok": r.status_code < 300, "status": r.status_code,
                "reason": None if r.status_code < 300 else r.text[:160]}
    except Exception as e:
        return {"ok": False, "reason": "%s: %s" % (type(e).__name__, e)}


@router.post("/jira/webhook")
async def jira_webhook(request: Request, org: str = "", token: str = "",
                       session: AsyncSession = Depends(get_session)):
    secret = settings.WEBHOOK_SECRET or ""
    supplied = token or request.headers.get("X-Webhook-Token") or ""
    if not secret or not hmac.compare_digest(supplied, secret):
        return JSONResponse({"ok": False, "reason": "invalid or missing webhook token"},
                            status_code=401)
    slug = org or request.query_params.get("org") or ""
    organization = (await session.execute(select(Organization).where(
        Organization.slug == slug))).scalar_one_or_none()
    if organization is None:
        return JSONResponse({"ok": False, "reason": "unknown org '%s'" % slug},
                            status_code=404)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    event = payload.get("webhookEvent") or ""
    issue = payload.get("issue") or {}
    key = issue.get("key")
    fields = issue.get("fields") or {}
    status_name = ((fields.get("status") or {}).get("name") or "")
    to_status = ""
    for it in ((payload.get("changelog") or {}).get("items") or []):
        if (it.get("field") or "").lower() == "status":
            to_status = it.get("toString") or to_status
    effective = (to_status or status_name or "").strip()
    is_approval = effective.lower() in APPROVAL_STATES

    await session.execute(text(_DDL))
    acted = "recorded"
    comment = None
    if is_approval and key:
        comment = await _post_comment(session, organization, key,
            "OpenLegal received your approval. The obligation tracked by %s is marked "
            "APPROVED via an inbound Jira webhook (status: %s). Posted back automatically "
            "by OpenLegal agreement monitoring." % (key, effective))
        acted = "commented" if comment.get("ok") else "comment_failed"
    await session.execute(text(
        "INSERT INTO jira_webhook_events "
        "(org_id, issue_key, event, status, is_approval, acted, raw_summary) "
        "VALUES (:o,:k,:e,:s,:a,:act,:r)"),
        {"o": str(organization.id), "k": key, "e": event, "s": effective,
         "a": is_approval, "act": acted,
         "r": ("%s %s -> %s" % (event, key or "?", effective))[:500]})
    await session.commit()
    return {"ok": True, "event": event, "issue": key, "status": effective,
            "is_approval": is_approval, "acted": acted, "comment": comment,
            "org": slug}


@router.get("/jira/webhook/events")
async def list_webhook_events(org=Depends(get_current_org),
                              session: AsyncSession = Depends(get_session)):
    await session.execute(text(_DDL))
    rows = (await session.execute(text(
        "SELECT issue_key, event, status, is_approval, acted, received_at "
        "FROM jira_webhook_events WHERE org_id = :o "
        "ORDER BY received_at DESC LIMIT 50"), {"o": str(org.id)})).mappings().all()
    return {"events": [dict(r) for r in rows]}
