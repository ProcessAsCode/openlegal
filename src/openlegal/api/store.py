"""Human surface over the e-Līgumi agreement store.

The OpenLegal app proxies the UI's calls here so the browser talks to one
origin, one auth, one product. The store's API key never leaves the server.

Note the asymmetry, which is the point: the *agent* reaches the store
through read-only `uas.*` capabilities, while these endpoints — used only by
a person clicking in the UI — may also write. A planner has no path to them.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from openlegal.core.config import settings
from openlegal.deps import get_current_org
from openlegal.models.organization import Organization

router = APIRouter()


def _client(timeout: float = 30) -> httpx.AsyncClient:
    headers = {}
    if settings.ELIGUMI_API_KEY:
        headers["x-api-key"] = settings.ELIGUMI_API_KEY
    return httpx.AsyncClient(base_url=settings.ELIGUMI_BASE_URL.rstrip("/"),
                             headers=headers, timeout=timeout)


async def _passthrough(method: str, path: str, **kw) -> Any:
    try:
        async with _client(kw.pop("timeout", 30)) as c:
            r = await c.request(method, path, **kw)
    except httpx.HTTPError as exc:
        raise HTTPException(503, f"Līgumu krātuve nav sasniedzama: {type(exc).__name__}")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text[:300])
        except Exception:  # noqa: BLE001
            detail = r.text[:300]
        raise HTTPException(r.status_code, detail)
    return r


@router.get("/agreements", summary="Agreements held in the UAS store")
async def list_agreements(status: str | None = None,
                          org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", "/api/agreements",
                           params={"status": status} if status else None)
    return r.json()


@router.get("/agreements/{agreement_id}")
async def get_agreement(agreement_id: int, version: int | None = None,
                        org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", f"/api/agreements/{agreement_id}",
                           params={"version": version} if version else None)
    return r.json()


@router.get("/agreements/{agreement_id}/versions")
async def versions(agreement_id: int, org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", f"/api/agreements/{agreement_id}/versions")
    return r.json()


@router.get("/agreements/{agreement_id}/v{version}/xml")
async def xml(agreement_id: int, version: int,
              org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", f"/api/agreements/{agreement_id}/v{version}/xml")
    return Response(content=r.content, media_type="application/xml",
                    headers={"Content-Disposition": r.headers.get(
                        "content-disposition", "attachment")})


@router.get("/config")
async def config(org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", "/api/config")
    return r.json()


@router.post("/agreements/preview")
async def preview(request: Request, org: Organization = Depends(get_current_org)):
    r = await _passthrough("POST", "/api/agreements/preview", json=await request.json())
    return r.json()


@router.post("/agreements")
async def save(request: Request, org: Organization = Depends(get_current_org)):
    r = await _passthrough("POST", "/api/agreements", json=await request.json())
    return r.json()


@router.delete("/agreements/{agreement_id}")
async def delete(agreement_id: int, org: Organization = Depends(get_current_org)):
    r = await _passthrough("DELETE", f"/api/agreements/{agreement_id}")
    return r.json()


@router.post("/agreements/import")
async def start_import(file: UploadFile | None = File(default=None),
                       text: str = Form(default=""), profile: str = Form(default=""),
                       org: Organization = Depends(get_current_org)):
    files = {"file": (file.filename, await file.read(),
                      file.content_type or "application/octet-stream")} if file else None
    r = await _passthrough("POST", "/api/agreements/import", files=files,
                           data={"text": text, "profile": profile}, timeout=120)
    return r.json()


@router.get("/agreements/import/{job_id}")
async def import_status(job_id: str, org: Organization = Depends(get_current_org)):
    r = await _passthrough("GET", f"/api/agreements/import/{job_id}")
    return r.json()
