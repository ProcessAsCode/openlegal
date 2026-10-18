"""HTTP client for VeriDocs SDK sidecar — OpenLegal integration.

Mirrors the OpenDMS sdk_client pattern. Each significant incident-lifecycle
event is anchored as a signed Verifiable Credential through the SDK:

    OpenLegal API -> /api/documents/create -> SDK -> Register

The SDK signs with the org's local key (JsonWebSignature2020 / ES256K),
registers the VC reference with the VeriDocs Register, and returns the
document DID + VC payload. We persist that into the vc_references table
and link case_events.vc_reference_id to it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from openlegal.core.config import settings

logger = logging.getLogger(__name__)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        headers: dict[str, str] = {}
        api_key = getattr(settings, "SDK_API_KEY", "") or ""
        if api_key:
            headers["x-api-key"] = api_key
        _client = httpx.AsyncClient(
            base_url=settings.SDK_URL,
            timeout=15.0,
            headers=headers,
        )
    return _client


def _build_headers(trace_id: str | None, actor: dict[str, Any] | None) -> dict[str, str]:
    tid = trace_id or str(uuid.uuid4())
    h = {"X-Trace-Id": tid, "X-Actor-App": "openlegal"}
    if actor:
        if actor.get("id") is not None:
            h["X-Actor-User-Id"] = str(actor["id"])
        if actor.get("email"):
            h["X-Actor-Email"] = str(actor["email"])
        if actor.get("label"):
            h["X-Actor-Label"] = str(actor["label"])
    return h


async def health() -> dict[str, Any] | None:
    try:
        r = await _get_client().get("/api/health")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("SDK health failed: %s", e)
        return None


async def setup_status() -> dict[str, Any] | None:
    try:
        r = await _get_client().get("/api/setup/status")
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("SDK setup_status failed: %s", e)
        return None


async def sign_incident_event(
    *,
    case_number: str,
    event_type: str,
    claims: dict[str, Any],
    trace_id: str | None = None,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Issue a signed VC for one incident-lifecycle event.

    Implemented via /api/documents/create — the SDK treats each event as a
    content-addressable signed artifact in the VeriDocs Register. The
    document title encodes the event type for human-readable audit; the
    metadata holds the event-specific claims.

    Returns:
        {
          "vc_id": str,           # SDK doc_did, used as the VC identifier
          "issuer_did": str,
          "subject_did": str,     # same as vc_id for incident-event artifacts
          "vc_hash": str,
          "raw": dict,            # full SDK response for audit
        }
        or None on failure (signing is best-effort — failures degrade
        gracefully; the case still proceeds, just without a VC anchor).
    """
    body = {
        "title": f"{event_type} :: {case_number}",
        "classification": event_type,
        "registrationNumber": case_number,
        "metadata": {
            "app": "openlegal",
            "case_number": case_number,
            "event_type": event_type,
            **claims,
        },
    }
    try:
        r = await _get_client().post(
            "/api/documents/create",
            json=body,
            headers=_build_headers(trace_id, actor),
        )
    except Exception as e:
        logger.warning("SDK sign %s/%s exception: %s", event_type, case_number, e)
        return None

    if r.status_code not in (200, 201):
        logger.warning(
            "SDK sign %s/%s returned %d: %s",
            event_type, case_number, r.status_code, r.text[:200],
        )
        return None

    raw = r.json()
    # SDK responses typically carry doc_did / docDid / id at the top level.
    vc_id = (
        raw.get("doc_did")
        or raw.get("docDid")
        or raw.get("id")
        or raw.get("document", {}).get("did")
    )
    issuer = (
        raw.get("issuer_did")
        or raw.get("issuerDid")
        or raw.get("vc", {}).get("issuer")
    )
    # SDK sometimes returns {"id": "did:..."} instead of plain string.
    if isinstance(issuer, dict):
        issuer = issuer.get("id") or issuer.get("did")
    vc_hash = raw.get("vc_hash") or raw.get("vcHash") or raw.get("hash")

    if not vc_id:
        logger.warning("SDK sign %s/%s: no vc_id in response", event_type, case_number)
        return None

    return {
        "vc_id": str(vc_id),
        "issuer_did": str(issuer) if issuer else "did:web:openlegal.local",
        "subject_did": str(vc_id),
        "vc_hash": str(vc_hash) if vc_hash else None,
        "raw": raw,
    }


async def verify_vc(credential: dict[str, Any]) -> dict[str, Any] | None:
    try:
        r = await _get_client().post("/api/vc/verify", json={"credential": credential})
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("SDK verify_vc failed: %s", e)
        return None


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
