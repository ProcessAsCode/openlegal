"""JSON API over the UAS agreement store.

This service has no web UI. The human surface lives in the OpenLegal app
(Līgumu pārvaldības aģents); this container owns the data and the UAS
rules, and nothing else.

Two classes of caller, deliberately separated:

  read endpoints    the agent's `uas.*` capabilities and the UI's lists
  write endpoints   the UI only, on behalf of a named human. The agent has
                    no write capability pointed here, so a planner cannot
                    change an agreement no matter what it decides.

"Save" never overwrites: it appends v(n+1) and moves the current pointer.
"""

from __future__ import annotations

import io
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlmodel import Session, select

from db import engine, get_session_dep
from models import Agreement, AgreementRevision, Tenant
from uas import bootstrap as uas_bootstrap
from uas import parse as uas_parse
from uas import serialize as uas_serialize
from uas import validate as uas_validate
from uas.store import LocalAgreementStore
from tenant import TENANT_SLUG, api_key_ok

router = APIRouter(dependencies=[Depends(api_key_ok)])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _tid(s: Session) -> int:
    t = s.exec(select(Tenant).where(Tenant.slug == TENANT_SLUG)).first()
    if t is None:
        raise HTTPException(404, "tenant not initialised")
    return t.id


def _store(s: Session) -> LocalAgreementStore:
    return LocalAgreementStore(s)


def _meta(a: Agreement) -> dict[str, Any]:
    return {
        "id": a.id, "uas_id": a.uas_id, "title": a.title,
        "agreement_type": a.agreement_type, "profile": a.profile,
        "language": a.language, "status": a.status,
        "buyer_name": a.buyer_name, "supplier_name": a.supplier_name,
        "clause_count": a.clause_count,
        "standardization_ratio": a.standardization_ratio,
        "current_version": a.current_version, "source": a.source,
        "needs_review": a.needs_review,
        "validation": {
            "ok": a.last_validation_ok,
            "errors": a.last_validation_errors,
            "warnings": a.last_validation_warnings,
        },
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _get(s: Session, agreement_id: int) -> Agreement:
    a = _store(s).get(_tid(s), agreement_id)
    if a is None:
        raise HTTPException(404, "agreement not found")
    return a


def _as_text(xml) -> str:
    return xml.decode("utf-8") if isinstance(xml, (bytes, bytearray)) else xml


# --------------------------------------------------------------------------
# read
# --------------------------------------------------------------------------

@router.get("/agreements")
def list_agreements(status: str | None = None, limit: int = 200,
                    s: Session = Depends(get_session_dep)):
    rows = _store(s).list(_tid(s), status=status)[:min(limit, 500)]
    return {"tenant": TENANT_SLUG, "count": len(rows),
            "agreements": [_meta(a) for a in rows]}


@router.get("/agreements/{agreement_id}")
def get_agreement(agreement_id: int, version: int | None = None,
                  s: Session = Depends(get_session_dep)):
    a = _get(s, agreement_id)
    v = version or a.current_version
    xml = _store(s).revision_xml(_tid(s), a.id, v)
    if xml is None:
        raise HTTPException(404, f"version {v} not found")
    data = uas_parse.parse(xml)
    res = uas_validate.validate(xml)
    return {**_meta(a), "version": v, "uas": data,
            "summary": uas_parse.summarize(data),
            "findings": res.to_json(),
            "xml_url": f"/api/agreements/{a.id}/v{v}/xml"}


@router.get("/agreements/{agreement_id}/versions")
def list_versions(agreement_id: int, s: Session = Depends(get_session_dep)):
    a = _get(s, agreement_id)
    revs = _store(s).list_revisions(_tid(s), a.id)
    return {"id": a.id, "uas_id": a.uas_id, "current_version": a.current_version,
            "versions": [{
                "version": r.version, "change_note": getattr(r, "change_note", None),
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            } for r in revs]}


@router.get("/agreements/{agreement_id}/v{version}/xml")
def get_xml(agreement_id: int, version: int, s: Session = Depends(get_session_dep)):
    a = _get(s, agreement_id)
    xml = _store(s).revision_xml(_tid(s), a.id, version)
    if xml is None:
        raise HTTPException(404, f"version {version} not found")
    return Response(content=xml, media_type="application/xml",
                    headers={"Content-Disposition":
                             f'attachment; filename="{a.uas_id}-v{version}.xml"'})


@router.get("/config")
def config(version: str | None = None):
    v = version or uas_bootstrap.DEFAULT_VERSION
    return {"uas_versions": uas_bootstrap.available_versions(), "version": v,
            "profiles": uas_bootstrap.list_profiles(v),
            "clause_library": uas_bootstrap.list_clause_library(v),
            "tree": uas_bootstrap.tree_status(v)}


# --------------------------------------------------------------------------
# write — UI only, always on behalf of a human
# --------------------------------------------------------------------------

@router.post("/agreements/preview")
async def preview(request: Request):
    """Serialize + validate without persisting. Powers the live editor."""
    payload = await request.json()
    try:
        xml = uas_serialize.serialize(payload.get("data") or {})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Serializācijas kļūda: {exc}")
    res = uas_validate.validate(xml)
    return {"ok": res.ok, "xml": _as_text(xml), "findings": res.to_json(),
            "errors": len(res.errors), "warnings": len(res.warnings)}


@router.post("/agreements")
async def create_or_update(request: Request, s: Session = Depends(get_session_dep)):
    """Create an agreement, or append a version to an existing one.

    Accepts either a UAS data object (`data`) or raw canonical XML (`xml`).
    """
    payload = await request.json()
    raw_xml = payload.get("xml")
    if raw_xml:
        xml = raw_xml.encode("utf-8") if isinstance(raw_xml, str) else raw_xml
    else:
        try:
            xml = uas_serialize.serialize(payload.get("data") or {})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Serializācijas kļūda: {exc}")
    res = uas_validate.validate(xml)
    store = _store(s)
    tid = _tid(s)
    aid = payload.get("agreement_id")
    if aid:
        ag = store.get(tid, int(aid))
        if ag is None:
            raise HTTPException(404, "agreement not found")
        if ag.needs_review:
            ag.needs_review = False  # a human saved it; the AI draft flag clears
        rev = store.save_version(agreement=ag, xml=xml, user_id=None,
                                 change_note=payload.get("change_note"), validation=res)
        version = rev.version
    else:
        ag = store.create(tenant_id=tid, xml=xml, user_id=None,
                          source=payload.get("source") or "manual",
                          needs_review=False, validation=res)
        version = ag.current_version
    return {"ok": True, "agreement_id": ag.id, "uas_id": ag.uas_id, "version": version,
            "validation": {"ok": res.ok, "errors": len(res.errors),
                           "warnings": len(res.warnings)},
            "findings": res.to_json()}


@router.delete("/agreements/{agreement_id}")
def soft_delete(agreement_id: int, s: Session = Depends(get_session_dep)):
    ok = _store(s).soft_delete(_tid(s), agreement_id)
    if not ok:
        raise HTTPException(404, "agreement not found")
    return {"ok": True, "deleted": agreement_id}


# --------------------------------------------------------------------------
# import — text/XML needs no model; docx/pdf extraction does
# --------------------------------------------------------------------------

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _job_set(job_id: str, **fields):
    with _JOBS_LOCK:
        _JOBS.setdefault(job_id, {"ts": time.time()}).update(fields)


def _extract_text(upload: UploadFile | None, raw: bytes, pasted: str) -> tuple[str, str]:
    if pasted and pasted.strip():
        return pasted, "pasted-text"
    name = (upload.filename if upload else "") or "upload"
    low = name.lower()
    if low.endswith(".docx"):
        try:
            import docx  # python-docx
            d = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in d.paragraphs), name
        except Exception:  # noqa: BLE001
            import re
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml), name
    if low.endswith(".pdf"):
        from pdfminer.high_level import extract_text as pdf_text
        return pdf_text(io.BytesIO(raw)) or "", name
    return raw.decode("utf-8", "ignore"), name


def _run_job(job_id: str, text: str, source_name: str, profile: str | None, tid: int):
    try:
        from uas import extract as uas_extract
        data = uas_extract.extract(text, source_name)
        if profile:
            data["profile"] = profile
        xml = uas_serialize.serialize(data)
        res = uas_validate.validate(xml)
        with Session(engine) as sess:
            ag = LocalAgreementStore(sess).create(
                tenant_id=tid, xml=xml, user_id=None, source="import",
                needs_review=True, validation=res)
            _job_set(job_id, status="done", agreement_id=ag.id, uas_id=ag.uas_id,
                     errors=len(res.errors), warnings=len(res.warnings))
    except Exception as exc:  # noqa: BLE001
        _job_set(job_id, status="error", error=str(exc)[:400])


@router.post("/agreements/import")
async def start_import(file: UploadFile | None = File(default=None),
                       text: str = Form(default=""), profile: str = Form(default=""),
                       s: Session = Depends(get_session_dep)):
    """Two paths. Canonical UAS XML is stored directly — no model involved.
    Anything else goes to the extractor, which needs an LLM provider."""
    raw = await file.read() if file is not None else b""
    name = (file.filename if file else "") or ""
    if name.lower().endswith(".xml") or (raw[:200].lstrip().startswith(b"<?xml") if raw else False):
        res = uas_validate.validate(raw)
        ag = _store(s).create(tenant_id=_tid(s), xml=raw, user_id=None,
                              source="import", needs_review=not res.ok, validation=res)
        return {"mode": "xml", "status": "done", "agreement_id": ag.id,
                "uas_id": ag.uas_id, "errors": len(res.errors),
                "warnings": len(res.warnings)}
    body, source_name = _extract_text(file, raw, text)
    if not body.strip():
        raise HTTPException(400, "Nav teksta, ko importēt.")
    job_id = uuid.uuid4().hex[:12]
    _job_set(job_id, status="running", source=source_name)
    tid = _tid(s)
    threading.Thread(target=_run_job, args=(job_id, body, source_name, profile or None, tid),
                     daemon=True).start()
    return {"mode": "extract", "status": "running", "job_id": job_id}


@router.get("/agreements/import/{job_id}")
def import_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "unknown job")
    return job
