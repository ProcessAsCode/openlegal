"""Systems connector to the e-Līgumi store (component C5).

Read-only by construction: the store exposes no write endpoint, and these
handlers do not attempt one. The agent's derived view lives in
`legal_agreements` (source_uas_id / uas_version), written by `register.sync`.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select

from openlegal.core.config import settings
from openlegal.models.legal_agreement import AgreementStatus, LegalAgreement


def _client() -> httpx.AsyncClient:
    headers = {}
    if settings.ELIGUMI_API_KEY:
        headers["x-api-key"] = settings.ELIGUMI_API_KEY
    return httpx.AsyncClient(base_url=settings.ELIGUMI_BASE_URL.rstrip("/"),
                             headers=headers, timeout=30)


async def uas_list(session, org, inputs, context) -> dict[str, Any]:
    params = {}
    if inputs.get("status"):
        params["status"] = inputs["status"]
    async with _client() as c:
        r = await c.get("/api/agreements", params=params)
    r.raise_for_status()
    body = r.json()
    return {"count": body.get("count", 0), "agreements": [
        {k: a.get(k) for k in ("id", "uas_id", "title", "agreement_type", "status",
                               "buyer_name", "supplier_name", "current_version", "needs_review")}
        for a in body.get("agreements", [])], "source": "eligumi"}


async def uas_read(session, org, inputs, context) -> dict[str, Any]:
    ref = inputs.get("agreement_id") or inputs.get("id") or inputs.get("uas_id")
    if ref is None:
        raise ValueError("uas.read: agreement_id (numeric id or uas_id) is required")
    async with _client() as c:
        if isinstance(ref, int) or str(ref).isdigit():
            r = await c.get(f"/api/agreements/{int(ref)}",
                            params={"version": inputs["version"]} if inputs.get("version") else None)
        else:
            lst = await c.get("/api/agreements")
            lst.raise_for_status()
            match = next((a for a in lst.json().get("agreements", []) if a.get("uas_id") == ref), None)
            if match is None:
                return {"found": False, "ref": ref}
            r = await c.get(f"/api/agreements/{match['id']}")
    if r.status_code == 404:
        return {"found": False, "ref": ref}
    r.raise_for_status()
    body = r.json()
    return {"found": True, "id": body["id"], "uas_id": body["uas_id"], "version": body["version"],
            "title": body["title"], "status": body["status"], "uas": body.get("uas"),
            "source": "eligumi"}


async def register_sync(session, org, inputs, context) -> dict[str, Any]:
    """Mirror one store agreement into the Agreement Register (derived view)."""
    doc = await uas_read(session, org, inputs, context)
    if not doc.get("found"):
        return doc
    uas = doc.get("uas") or {}
    stmt = select(LegalAgreement).where(LegalAgreement.org_id == org.id,
                                        LegalAgreement.agreement_id == doc["uas_id"])
    row = (await session.execute(stmt)).scalar_one_or_none()
    status_map = {"active": AgreementStatus.ACTIVE, "expired": AgreementStatus.EXPIRED,
                  "draft": AgreementStatus.DRAFT, "terminated": AgreementStatus.ARCHIVED,
                  "completed": AgreementStatus.ARCHIVED}
    if row is None:
        row = LegalAgreement(org_id=org.id, agreement_id=doc["uas_id"], title=doc["title"] or doc["uas_id"],
                             status=status_map.get(doc["status"], AgreementStatus.ACTIVE), uas=uas)
        session.add(row)
    else:
        row.title = doc["title"] or row.title
        row.status = status_map.get(doc["status"], row.status)
        row.uas = uas
    row.source_uas_id = str(doc["id"])
    row.uas_version = int(doc["version"])
    await session.flush()
    return {"synced": True, "register_id": str(row.id), "uas_id": doc["uas_id"], "version": doc["version"]}
