"""intake UAPF capability: intake.normalize.

Source-specific extractors pull semantic fields out of raw adapter payloads
into the canonical OpenLegal signal schema.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.organization import Organization
from openlegal.models.signal import Signal, SignalSource, SignalStatus


async def normalize(
    session: AsyncSession,
    org: Organization,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    signal_id = uuid.UUID(inputs["signal_id"])
    signal = await session.get(Signal, signal_id)
    if signal is None or signal.org_id != org.id:
        raise LookupError(f"intake.normalize: signal {signal_id} not found in org {org.slug}")

    normalized = _normalize_payload(signal.source, signal.raw_payload or {})
    if not signal.dedupe_hash:
        signal.dedupe_hash = _dedupe_hash(signal.source, normalized)

    signal.normalized_payload = normalized
    signal.normalized_at = datetime.now(timezone.utc)
    if signal.status == SignalStatus.RECEIVED:
        signal.status = SignalStatus.NORMALIZED

    return {
        "signal_id": str(signal.id),
        "normalized": True,
        "normalized_payload": normalized,
        "dedupe_hash": signal.dedupe_hash,
    }


def _normalize_payload(source: SignalSource, raw: dict[str, Any]) -> dict[str, Any]:
    fn = _NORMALIZERS.get(source, _normalize_generic)
    out = fn(raw)
    canonical = {
        "title": None, "description": None, "severity": None,
        "host": None, "service": None, "tags": [],
        "raw_keys": list(raw.keys()) if isinstance(raw, dict) else [],
    }
    canonical.update(out)
    return canonical


def _normalize_zabbix(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": raw.get("title") or raw.get("name") or raw.get("description"),
        "description": raw.get("body") or raw.get("description"),
        "severity": (raw.get("severity") or "").lower() or None,
        "host": raw.get("host") or raw.get("hostname"),
        "service": raw.get("service"),
        "tags": list(raw.get("tags") or []),
        "zabbix_event_id": raw.get("event_id") or raw.get("eventid"),
    }


def _normalize_email(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": raw.get("subject"),
        "description": raw.get("body") or raw.get("text"),
        "host": None, "service": None,
        "email_from": raw.get("from") or raw.get("sender"),
        "email_to": raw.get("to") or raw.get("recipient"),
    }


def _normalize_jira(raw: dict[str, Any]) -> dict[str, Any]:
    fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
    return {
        "title": fields.get("summary") or fields.get("title"),
        "description": fields.get("description"),
        "severity": (fields.get("priority", {}) or {}).get("name", "").lower() or None,
        "tags": [c.get("name") for c in (fields.get("components") or []) if isinstance(c, dict)],
        "jira_key": raw.get("key"),
        "jira_status": (fields.get("status", {}) or {}).get("name"),
    }


def _normalize_manual(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": raw.get("title") or raw.get("summary"),
        "description": raw.get("description") or raw.get("body"),
        "host": raw.get("host"), "service": raw.get("service"),
        "tags": list(raw.get("tags") or []),
    }


def _normalize_generic(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": (raw.get("title") or raw.get("subject") or raw.get("summary")
                  or raw.get("message") or raw.get("name")),
        "description": raw.get("description") or raw.get("body") or raw.get("text"),
        "severity": (raw.get("severity") or "").lower() or None,
        "host": raw.get("host") or raw.get("hostname"),
        "service": raw.get("service"),
        "tags": list(raw.get("tags") or []),
    }


_NORMALIZERS = {
    SignalSource.ZABBIX: _normalize_zabbix,
    SignalSource.EMAIL: _normalize_email,
    SignalSource.JIRA_DC: _normalize_jira,
    SignalSource.JIRA_CLOUD: _normalize_jira,
    SignalSource.MANUAL: _normalize_manual,
}


def _dedupe_hash(source: SignalSource, normalized: dict[str, Any]) -> str:
    title = (normalized.get("title") or "").strip()
    title = " ".join(title.split())[:80].lower()
    parts = [source.value, normalized.get("host") or "",
             normalized.get("service") or "", title]
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:32]
