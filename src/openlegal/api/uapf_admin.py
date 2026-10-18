"""UAPF admin REST API — what the SPA's UAPF page uses.

Endpoints (all mounted under /api/uapf):
  GET    /packages                 list packages loaded in the engine + sources
  GET    /packages/{pid}/info      package metadata + decisions summary
  GET    /packages/{pid}/bpmn/{process_id}.xml   raw BPMN
  GET    /packages/{pid}/dmn/{decision_id}.xml   raw DMN
  GET    /packages/{pid}/algorithms              algorithm cards (UAPF 2.4+)
  GET    /sessions                 list uapf_sessions
  GET    /sessions/{sid}           session detail with audit chain
  GET    /demo-signals             curated list of demo signal fixtures
  POST   /run-demo                 run one demo signal end-to-end (creates case,
                                   runs triage, signs VCs, returns full chain)
  POST   /run-freetext             same but takes a user-typed title/body
  POST   /replay-case              replay-only: given an existing case_id,
                                   return the persisted audit chain + VCs in
                                   the shape the Demo Console expects.

Surfaces the engine package metadata + runtime sessions through a thin
REST layer the SPA can render.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from openlegal.core.config import settings
from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.case import Case
from openlegal.models.case_event import CaseEvent
from openlegal.models.organization import Organization
from openlegal.models.uapf_session import UAPFSession
from openlegal.models.vc_reference import VCReference

logger = logging.getLogger(__name__)
router = APIRouter()

# The container has the unpacked package under /app/uapf-packages.
PACKAGES_DIR = Path("/app/uapf-packages")
PKG_LV_ITSM_TRIAGE = "lv.itsm.incident.triage"


# ─── helpers ──────────────────────────────────────────────────────────

def _package_root(package_id: str) -> Path:
    """Return the unpacked package directory if present.

    Strategy: scan every subdir under /app/uapf-packages and pick the one
    whose manifest.json declares this package id. Falls back to literal
    name matches if no manifest is found. Prefers dirs with a bpmn/ subdir
    (the modern v1+ layout); older layouts that have process/ but no bpmn/
    only win if nothing better is present.
    """
    import json
    if not PACKAGES_DIR.is_dir():
        raise HTTPException(404, f"PACKAGES_DIR missing: {PACKAGES_DIR}")

    # First pass: read manifests and pick the dir whose manifest.id matches
    manifest_match: Path | None = None
    for sub in PACKAGES_DIR.iterdir():
        if not sub.is_dir():
            continue
        man = sub / "manifest.json"
        if not man.is_file():
            continue
        try:
            data = json.loads(man.read_text())
        except Exception:
            continue
        mid = data.get("id") or data.get("packageId")
        if mid == package_id:
            # Prefer one with bpmn/ if multiple manifests match
            if (sub / "bpmn").is_dir():
                return sub
            if manifest_match is None:
                manifest_match = sub
    if manifest_match is not None:
        return manifest_match

    # Fallback: literal directory name lookups
    short = package_id.rsplit(".", 1)[-1]
    for cand in (PACKAGES_DIR / short, PACKAGES_DIR / package_id):
        if cand.is_dir():
            return cand
    raise HTTPException(404, f"Package not found: {package_id}")


async def _engine_get(path: str) -> Any:
    """GET helper against the openlegal-uapf-engine; returns parsed JSON
    or raises HTTPException."""
    url = settings.UAPF_ENGINE_URL.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
    except Exception as e:
        raise HTTPException(502, f"Engine unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(r.status_code, f"Engine {path}: {r.text[:200]}")
    return r.json()


# ─── packages ─────────────────────────────────────────────────────────

@router.get("/packages")
async def list_packages(org: Organization = Depends(get_current_org)) -> dict[str, Any]:
    """Combines what's loaded in the engine with our local package metadata."""
    engine_packages: list[dict[str, Any]] = []
    engine_alive = False
    try:
        engine_packages = await _engine_get("/uapf/packages")
        engine_alive = True
    except HTTPException as e:
        logger.warning("Engine list_packages failed: %s", e.detail)

    return {
        "engine_alive": engine_alive,
        "engine_url": settings.UAPF_ENGINE_URL,
        "packages": engine_packages,
    }


@router.get("/packages/{package_id}/info")
async def package_info(
    package_id: str,
    org: Organization = Depends(get_current_org),
) -> dict[str, Any]:
    """High-level metadata about the package — name, description, process,
    decisions, capabilities. Drawn from the engine + the on-disk manifest."""
    import json
    root = _package_root(package_id)

    # Manifest
    manifest_path = root / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as e:
            logger.warning("manifest.json parse failed: %s", e)

    # Engine view (authoritative for process/decisions/triggers)
    engine_pkg: dict[str, Any] = {}
    try:
        all_pkgs = await _engine_get("/uapf/packages")
        for p in all_pkgs:
            if p.get("packageId") == package_id:
                engine_pkg = p
                break
    except HTTPException:
        pass

    # BPMN process id + decisions from the engine's parsed view if present;
    # otherwise reconstruct from disk by listing bpmn/ and dmn/ files.
    process = engine_pkg.get("process") or {}
    if not process:
        bpmn_dir = root / "bpmn"
        if bpmn_dir.is_dir():
            files = sorted(bpmn_dir.glob("*.bpmn"))
            if files:
                # Process id is the filename stem
                process = {"id": files[0].stem, "name": files[0].stem}

    decisions: list[dict[str, Any]] = engine_pkg.get("decisions") or []
    if not decisions:
        dmn_dir = root / "dmn"
        if dmn_dir.is_dir():
            for f in sorted(dmn_dir.glob("*.dmn")):
                decisions.append({"id": f.stem, "name": f.stem, "hitPolicy": "?", "rules": []})

    # Service tasks / capabilities — from manifest if present, else from engine
    capabilities = manifest.get("capabilities") or engine_pkg.get("capabilities") or []
    triggers = engine_pkg.get("triggers") or {"active": [], "all": []}

    return {
        "packageId": package_id,
        "version": manifest.get("version") or engine_pkg.get("version") or "?",
        "name": manifest.get("name") or engine_pkg.get("name") or package_id,
        "description": manifest.get("description") or engine_pkg.get("description") or "",
        "level": manifest.get("level") or engine_pkg.get("level") or 4,
        "manifest": manifest,
        "process": process,
        "decisions": decisions,
        "capabilities": capabilities,
        "triggers": triggers,
    }


@router.get("/packages/{package_id}/bpmn/{process_id}.xml")
async def get_bpmn_xml(
    package_id: str,
    process_id: str,
    org: Organization = Depends(get_current_org),
) -> Response:
    """Raw BPMN XML for the named process."""
    root = _package_root(package_id)
    bpmn_dir = root / "bpmn"
    if not bpmn_dir.is_dir():
        raise HTTPException(404, "No bpmn/ directory in package")
    # Prefer exact filename match, else first .bpmn whose name contains process_id
    exact = bpmn_dir / f"{process_id}.bpmn"
    if exact.is_file():
        target = exact
    else:
        candidates = [f for f in bpmn_dir.glob("*.bpmn") if process_id in f.name]
        if not candidates:
            # final fallback: the only bpmn file
            all_bpmn = list(bpmn_dir.glob("*.bpmn"))
            if len(all_bpmn) == 1:
                target = all_bpmn[0]
            else:
                raise HTTPException(404, f"No BPMN for process '{process_id}'")
        else:
            target = candidates[0]
    return Response(content=target.read_text(), media_type="application/xml")


@router.get("/packages/{package_id}/dmn/{decision_id}.xml")
async def get_dmn_xml(
    package_id: str,
    decision_id: str,
    org: Organization = Depends(get_current_org),
) -> Response:
    """Raw DMN XML for the named decision."""
    root = _package_root(package_id)
    dmn_dir = root / "dmn"
    if not dmn_dir.is_dir():
        raise HTTPException(404, "No dmn/ directory in package")
    exact = dmn_dir / f"{decision_id}.dmn"
    if exact.is_file():
        target = exact
    else:
        candidates = [f for f in dmn_dir.glob("*.dmn") if decision_id in f.name]
        if not candidates:
            raise HTTPException(404, f"No DMN for decision '{decision_id}'")
        target = candidates[0]
    return Response(content=target.read_text(), media_type="application/xml")


@router.get("/packages/{package_id}/algorithms")
async def list_algorithm_cards(
    package_id: str,
    org: Organization = Depends(get_current_org),
) -> dict[str, Any]:
    """List algorithm cards in the package (UAPF v2.4+ feature)."""
    import yaml
    root = _package_root(package_id)
    cards_dir = root / "algorithms"
    if not cards_dir.is_dir():
        return {"algorithms": []}
    cards: list[dict[str, Any]] = []
    for f in sorted(cards_dir.glob("*.card.yaml")):
        try:
            data = yaml.safe_load(f.read_text())
            if isinstance(data, dict) and data.get("id"):
                cards.append(data)
        except Exception as e:
            logger.warning("Failed to read card %s: %s", f.name, e)
    return {"algorithms": cards}


# ─── sessions ─────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    limit: int = 50,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    stmt = (
        select(UAPFSession)
        .where(UAPFSession.org_id == org.id)
        .order_by(desc(UAPFSession.started_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[dict[str, Any]] = []
    for s in rows:
        out.append({
            "session_id": s.session_id,
            "case_id": str(s.case_id) if s.case_id else None,
            "signal_id": str(s.signal_id) if s.signal_id else None,
            "package_id": s.package_id,
            "process_id": s.process_id,
            "trigger_name": s.trigger_name,
            "state": s.state.value if hasattr(s.state, "value") else str(s.state),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        })
    return out


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = (
        select(UAPFSession)
        .where(UAPFSession.org_id == org.id, UAPFSession.session_id == session_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Session {session_id} not found")

    # Audit chain from engine (best effort)
    audit_chain: list[dict[str, Any]] = []
    try:
        audit_chain = await _engine_get(f"/uapf/sessions/{session_id}/audit")
    except HTTPException:
        pass

    # Persisted events for this case (timeline)
    persisted: list[dict[str, Any]] = []
    if row.case_id:
        case_evt_stmt = (
            select(CaseEvent)
            .where(CaseEvent.case_id == row.case_id)
            .options(selectinload(CaseEvent.vc_reference))
            .order_by(CaseEvent.created_at.asc())
        )
        evts = (await session.execute(case_evt_stmt)).scalars().all()
        for e in evts:
            persisted.append({
                "id": str(e.id),
                "type": e.type.value if hasattr(e.type, "value") else str(e.type),
                "actor_type": e.actor_type.value if hasattr(e.actor_type, "value") else str(e.actor_type),
                "actor_label": e.actor_label,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "vc": ({
                    "vc_id": e.vc_reference.vc_id,
                    "vc_type": e.vc_reference.vc_type.value if hasattr(e.vc_reference.vc_type, "value") else str(e.vc_reference.vc_type),
                    "issuer_did": e.vc_reference.issuer_did,
                } if e.vc_reference else None),
            })

    return {
        "session_id": row.session_id,
        "case_id": str(row.case_id) if row.case_id else None,
        "package_id": row.package_id,
        "process_id": row.process_id,
        "trigger_name": row.trigger_name,
        "state": row.state.value if hasattr(row.state, "value") else str(row.state),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "input_payload": row.input_payload,
        "output_payload": row.output_payload,
        "audit_chain_engine": audit_chain,
        "audit_chain_persisted": persisted,
    }


# ─── demo signals + run-now ───────────────────────────────────────────

# Curated demo signal fixtures. Each one is hand-tuned so the live
# Anthropic classification produces the expected outputs — useful for
# the stage demo where Rihards wants predictable, well-formed results.
DEMO_SIGNALS: list[dict[str, Any]] = [
    {
        "id": "bgp-flap",
        "title": "BGP session flapping rtr-core-04 → AS3262",
        "body": "Repeated BGP state transitions on edge router to upstream AS3262 peer. Customer traffic experiencing reroutes. Started 14:02 UTC.",
        "source": "zabbix",
        "severity": "high",
        "host": "rtr-core-04.example.net",
        "expected": {"priority": "P1", "group": "noc-l2", "classification": "network.routing"},
    },
    {
        "id": "fiber-cesis",
        "title": "Šķiedras pārrāvums — klients nepieejams",
        "body": "Klients ziņo par pilnīgu pieslēguma zudumu reģionālā segmentā. Iespējams optiskās šķiedras bojājums starp diviem mezgliem.",
        "source": "email",
        "severity": "high",
        "host": "fiber-segment-region-a-to-b",
        "expected": {"priority": "P1", "group": "noc-l2", "classification": "network.outage.link_down"},
    },
    {
        "id": "ups-battery",
        "title": "UPS akumulators kritisks — DC-Primary rack B7",
        "body": "Datu centra rack B7 UPS akumulatora kapacitāte zem 30%. Automātiska pārslēgšanās uz tīkla barošanu neizdevās iepriekšējā testā.",
        "source": "zabbix",
        "severity": "medium",
        "host": "ups-b7.dc-primary.example.net",
        "expected": {"priority": "P2", "group": "facility-l2", "classification": "facility.power"},
    },
    {
        "id": "ddos-edge",
        "title": "DDoS attack pattern detected on edge — SYN flood 4 Gbps",
        "body": "Inbound SYN flood detected on edge router peering. Source IPs distributed across 12 ASNs. Traffic to 195.135.x.x range. Auto-scrub triggered.",
        "source": "zabbix",
        "severity": "high",
        "host": "edge-peer-01.example.net",
        "expected": {"priority": "P1", "group": "secops-l2", "classification": "security.incident"},
    },
    {
        "id": "customer-upgrade",
        "title": "Klients pieprasa joslas platuma palielinājumu no 1G uz 10G",
        "body": "Klients pieprasa internet uplink joslas platuma palielinājumu no 1 Gbps uz 10 Gbps. Esošais līgums Nr. AB-2024-0421.",
        "source": "email",
        "severity": "low",
        "host": None,
        "expected": {"priority": "P3", "group": "helpdesk-l1", "classification": "service.customer_request"},
    },
    {
        "id": "dns-latency",
        "title": "DNS resolution latency spike — dns-anycast-01",
        "body": "Recursive DNS resolver p95 latency jumped from 12ms to 380ms over last 5 min. Affects ~25% of customer DNS traffic. No upstream outage detected.",
        "source": "zabbix",
        "severity": "medium",
        "host": "dns-anycast-01.example.net",
        "expected": {"priority": "P2", "group": "noc-l2", "classification": "network.dns"},
    },
]


@router.get("/demo-signals")
async def list_demo_signals(org: Organization = Depends(get_current_org)) -> list[dict[str, Any]]:
    return DEMO_SIGNALS


class RunDemoBody(BaseModel):
    signal_id: str


@router.post("/run-demo")
async def run_demo_signal(
    body: RunDemoBody,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run a curated demo signal end-to-end. Creates a new case, runs full
    triage (real Anthropic classification + DMN + VC signing), and returns
    the assembled audit chain + classification result + VC chain so the
    SPA can animate the playback."""
    signal_def = next((s for s in DEMO_SIGNALS if s["id"] == body.signal_id), None)
    if not signal_def:
        raise HTTPException(404, f"Demo signal '{body.signal_id}' not found")

    return await _run_signal_and_collect(
        session=session,
        org=org,
        source=signal_def["source"],
        title=signal_def["title"],
        body=signal_def["body"],
        severity=signal_def["severity"],
        host=signal_def.get("host"),
        external_id=f"demo-{signal_def['id']}-{uuid.uuid4().hex[:8]}",
    )


class RunFreetextBody(BaseModel):
    title: str
    body: str
    severity: str = "medium"
    source: str = "manual"
    host: str | None = None


@router.post("/run-freetext")
async def run_freetext_signal(
    body: RunFreetextBody,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Same as /run-demo but takes user-typed title + body."""
    return await _run_signal_and_collect(
        session=session,
        org=org,
        source=body.source,
        title=body.title,
        body=body.body,
        severity=body.severity,
        host=body.host,
        external_id=f"demo-freetext-{uuid.uuid4().hex[:10]}",
    )


@router.get("/replay-case/{case_id}")
async def replay_case(
    case_id: uuid.UUID,
    org: Organization = Depends(get_current_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the persisted audit chain + VC chain for an existing case,
    in the shape the Demo Console expects so the SPA can animate it."""
    case_stmt = (
        select(Case)
        .where(Case.org_id == org.id, Case.id == case_id)
        .options(selectinload(Case.classification), selectinload(Case.assigned_group))
    )
    case = (await session.execute(case_stmt)).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")

    evt_stmt = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .options(selectinload(CaseEvent.vc_reference))
        .order_by(CaseEvent.created_at.asc())
    )
    events = (await session.execute(evt_stmt)).scalars().all()
    return _assemble_demo_response(case, events, source_label="replay")


# ─── helpers ──────────────────────────────────────────────────────────

async def _run_signal_and_collect(
    *,
    session: AsyncSession,
    org: Organization,
    source: str,
    title: str,
    body: str,
    severity: str,
    host: str | None,
    external_id: str,
) -> dict[str, Any]:
    """Shared path for /run-demo and /run-freetext.

    Calls into the same intake pipeline POST /api/intake/ uses (programmatic
    invocation, not HTTP-self-loopback), then collects the resulting case +
    events + VCs into a single response."""
    from openlegal.api.intake import _process_intake_payload
    from openlegal.schemas.signal import SignalCreate
    from openlegal.models.signal import SignalSource

    raw_payload: dict[str, Any] = {
        "title": title,
        "body": body,
        "severity": severity,
    }
    if host:
        raw_payload["host"] = host

    # SignalSource is an enum; map source string to enum member if possible,
    # falling back to MANUAL for anything we don't recognise.
    try:
        src_enum = SignalSource(source)
    except Exception:
        src_enum = SignalSource.MANUAL

    req = SignalCreate(
        source=src_enum,
        external_id=external_id,
        raw_payload=raw_payload,
    )
    result = await _process_intake_payload(req, session=session, org=org)
    if not result.triage:
        raise HTTPException(500, "Triage did not run — TRIAGE_AUTO may be off")
    # case_id may arrive as either str or asyncpg UUID; normalise via str()
    raw_case_id = result.triage.case_id
    case_id = raw_case_id if isinstance(raw_case_id, uuid.UUID) else uuid.UUID(str(raw_case_id))

    case_stmt = (
        select(Case)
        .where(Case.id == case_id)
        .options(selectinload(Case.classification), selectinload(Case.assigned_group))
    )
    case = (await session.execute(case_stmt)).scalar_one()

    evt_stmt = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .options(selectinload(CaseEvent.vc_reference))
        .order_by(CaseEvent.created_at.asc())
    )
    events = (await session.execute(evt_stmt)).scalars().all()
    return _assemble_demo_response(case, events, source_label="live")


def _assemble_demo_response(
    case: Case,
    events: list[CaseEvent],
    *,
    source_label: str,
) -> dict[str, Any]:
    # Classification may not be persisted on the case row (triage gap), so
    # fall back to the routed event payload which always carries it.
    classification_slug = case.classification.slug if case.classification else None
    if not classification_slug:
        for e in reversed(events):
            payload = e.payload or {}
            etype = e.type.value if hasattr(e.type, "value") else str(e.type)
            if etype == "routed" and isinstance(payload, dict) and payload.get("classification"):
                classification_slug = payload["classification"]
                break
    group_slug = case.assigned_group.slug if case.assigned_group else None

    timeline: list[dict[str, Any]] = []
    vc_chain: list[dict[str, Any]] = []
    for e in events:
        row: dict[str, Any] = {
            "id": str(e.id),
            "type": e.type.value if hasattr(e.type, "value") else str(e.type),
            "actor_type": e.actor_type.value if hasattr(e.actor_type, "value") else str(e.actor_type),
            "actor_label": e.actor_label,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        if e.vc_reference:
            vc = {
                "vc_id": e.vc_reference.vc_id,
                "vc_type": e.vc_reference.vc_type.value if hasattr(e.vc_reference.vc_type, "value") else str(e.vc_reference.vc_type),
                "issuer_did": e.vc_reference.issuer_did,
                "subject_did": e.vc_reference.subject_did,
                "vc_hash": e.vc_reference.vc_hash,
                "for_event_id": str(e.id),
                "for_event_type": row["type"],
            }
            row["vc"] = vc
            vc_chain.append(vc)
        timeline.append(row)

    return {
        "source": source_label,
        "case": {
            "id": str(case.id),
            "case_number": case.case_number,
            "title": case.title,
            "status": case.status.value if hasattr(case.status, "value") else str(case.status),
            "priority": case.priority.value if case.priority and hasattr(case.priority, "value") else (case.priority if case.priority else None),
            "classification": classification_slug,
            "group_slug": group_slug,
        },
        "timeline": timeline,
        "vc_chain": vc_chain,
    }
