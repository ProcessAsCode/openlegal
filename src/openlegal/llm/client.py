"""LLM client with provider abstraction + deterministic fallbacks.

Public surface — one async function per capability. Each function:
  1. Attempts the configured provider call (anthropic).
  2. On any failure (no key, network error, malformed JSON, ...) falls back
     to a deterministic stub that returns a sensibly-shaped response.

The handlers in uapf/handlers/ai.py call these functions and don't need
to care which path produced the answer.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from openlegal.core.config import settings
from openlegal.llm import prompts


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider client (lazy, cached, async)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _anthropic_client():
    """Lazy-import the Anthropic SDK so the stub path works without it."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        logger.warning("anthropic package not installed; using stub fallback")
        return None
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _call_anthropic_json(
    system: str, user: str, *, max_tokens: int = 1024,
) -> dict[str, Any]:
    """One JSON completion through the configured provider (name kept for
    the call sites; it is no longer Anthropic-specific)."""
    from openlegal.llm import provider
    return await provider.complete_json(system, user, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Public capability functions
# ---------------------------------------------------------------------------

async def classify_text(text: str) -> dict[str, Any]:
    """Classify an incident text into a taxonomy code.

    Returns: {taxonomy_code, label_hint, confidence, reasoning?}.
    """
    if _anthropic_enabled():
        try:
            data = await _call_anthropic_json(
                prompts.classify_system(),
                prompts.classify_user(text),
                max_tokens=256,
            )
            code = data.get("taxonomy_code")
            if code in prompts.TAXONOMY_CODES:
                return {
                    "taxonomy_code": code,
                    "label_hint": code.split(".")[-1].replace("_", " "),
                    "confidence": float(data.get("confidence", 0.7)),
                    "reasoning": data.get("reasoning", "")[:280],
                    "_via": "anthropic",
                }
        except Exception as exc:
            logger.warning("classify_text: anthropic failed, stub fallback: %s", exc)
    return _stub_classify(text)


async def suggest_priority(
    severity: str | None, service_tier: str | None, classification: str | None,
) -> dict[str, Any]:
    """Suggest P1..P4 priority. Returns {priority, reason}."""
    severity = severity or "average"
    service_tier = service_tier or "tier_2"
    classification = classification or "unknown.uncategorized"

    if _anthropic_enabled():
        try:
            data = await _call_anthropic_json(
                prompts.suggest_priority_system(),
                prompts.suggest_priority_user(severity, service_tier, classification),
                max_tokens=200,
            )
            prio = data.get("priority")
            if prio in {"P1", "P2", "P3", "P4"}:
                return {
                    "priority": prio,
                    "reason": data.get("reason", "")[:280],
                    "_via": "anthropic",
                }
        except Exception as exc:
            logger.warning("suggest_priority: anthropic failed, stub fallback: %s", exc)
    return _stub_priority(severity, service_tier, classification)


async def draft_response(
    org_slug: str, what_happened: str, eta_minutes: int | None,
    locale: str = "lv",
) -> dict[str, Any]:
    """Draft a customer notification (LV + EN bodies)."""
    if _anthropic_enabled():
        try:
            data = await _call_anthropic_json(
                prompts.draft_response_system(org_slug),
                prompts.draft_response_user(what_happened, eta_minutes),
                max_tokens=1024,
            )
            req = ("subject_lv", "subject_en", "body_lv", "body_en")
            if all(k in data and isinstance(data[k], str) for k in req):
                data["locale"] = locale
                data["_via"] = "anthropic"
                return data
        except Exception as exc:
            logger.warning("draft_response: anthropic failed, stub fallback: %s", exc)
    return _stub_draft_response(org_slug, what_happened, eta_minutes, locale)


async def summarize_timeline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a case timeline into 2-3 sentences."""
    if _anthropic_enabled():
        try:
            data = await _call_anthropic_json(
                prompts.summarize_timeline_system(),
                prompts.summarize_timeline_user(events),
                max_tokens=400,
            )
            if isinstance(data.get("summary"), str):
                return {
                    "summary": data["summary"],
                    "event_count": len(events),
                    "_via": "anthropic",
                }
        except Exception as exc:
            logger.warning("summarize_timeline: anthropic failed, stub fallback: %s", exc)
    return _stub_summarize(events)


async def extract_root_cause(text: str) -> dict[str, Any]:
    """Extract a root-cause hypothesis from artifacts."""
    if _anthropic_enabled():
        try:
            data = await _call_anthropic_json(
                prompts.extract_root_cause_system(),
                prompts.extract_root_cause_user(text),
                max_tokens=512,
            )
            if isinstance(data.get("hypothesis"), str):
                return {
                    "hypothesis": data["hypothesis"],
                    "evidence_keywords": data.get("evidence_keywords", [])[:20],
                    "confidence": float(data.get("confidence", 0.5)),
                    "_via": "anthropic",
                }
        except Exception as exc:
            logger.warning("extract_root_cause: anthropic failed, stub fallback: %s", exc)
    return _stub_root_cause(text)


# ---------------------------------------------------------------------------
# Provider gating
# ---------------------------------------------------------------------------

def _anthropic_enabled() -> bool:
    from openlegal.llm import provider
    return provider.enabled()


# ---------------------------------------------------------------------------
# Deterministic stubs (the fallback path)
# ---------------------------------------------------------------------------

_CLASSIFY_KEYWORDS: list[tuple[str, str]] = [
    (r"\blink\b.*\bdown\b|interface .* down|\bge-\d", "network.outage.link_down"),
    (r"power|electricity|ups|generator|battery", "facility.power"),
    (r"latency|slow|jitter|packet loss|degraded", "network.degradation"),
    (r"ddos|attack|exploit|breach|intrusion", "security.incident"),
    (r"disk full|out of space|inode|quota", "storage.capacity"),
    (r"\bdns\b|resolv|bind", "network.dns"),
    (r"router|switch|bgp|ospf", "network.routing"),
    (r"customer|klient", "service.customer_request"),
]


def _stub_classify(text: str) -> dict[str, Any]:
    lo = (text or "").lower()
    for pat, code in _CLASSIFY_KEYWORDS:
        if re.search(pat, lo):
            return {
                "taxonomy_code": code,
                "label_hint": code.split(".")[-1].replace("_", " "),
                "confidence": 0.75,
                "_via": "stub",
            }
    return {
        "taxonomy_code": "unknown.uncategorized",
        "label_hint": "uncategorized",
        "confidence": 0.2,
        "_via": "stub",
    }


def _stub_priority(severity: str, service_tier: str, classification: str) -> dict[str, Any]:
    sev = severity.lower()
    tier = service_tier.lower()
    cls = classification.lower()

    if sev in {"disaster", "critical"} or cls.startswith("security.incident"):
        return {"priority": "P1", "reason": "disaster/critical severity or security incident", "_via": "stub"}
    if sev == "high" and tier == "tier_1":
        return {"priority": "P1", "reason": "high severity on tier_1 service", "_via": "stub"}
    if sev == "high":
        return {"priority": "P2", "reason": "high severity", "_via": "stub"}
    if sev == "average" and tier == "tier_1":
        return {"priority": "P2", "reason": "average severity on tier_1 service", "_via": "stub"}
    if sev in {"average", "warning"}:
        return {"priority": "P3", "reason": "average/warning severity", "_via": "stub"}
    return {"priority": "P4", "reason": "low/info severity", "_via": "stub"}


def _stub_draft_response(
    org_slug: str, what_happened: str, eta_minutes: int | None, locale: str,
) -> dict[str, Any]:
    body_lv = (
        f"Labdien,\n\nMūsu komanda ir saņēmusi paziņojumu par {what_happened}. "
        f"Šobrīd notiek izpēte un risināšana."
    )
    if eta_minutes:
        body_lv += f" Aptuvenais risināšanas laiks: {eta_minutes} min."
    body_lv += f"\n\nAr cieņu,\n{org_slug.upper()} tehniskā atbalsta dienests"

    body_en = (
        f"Hello,\n\nOur team has received a notification about {what_happened}. "
        f"We are currently investigating and working on a fix."
    )
    if eta_minutes:
        body_en += f" Estimated resolution time: {eta_minutes} minutes."
    body_en += f"\n\nKind regards,\n{org_slug.upper()} Technical Support"

    return {
        "subject_lv": f"[{org_slug.upper()}] Informējam par incidentu",
        "subject_en": f"[{org_slug.upper()}] Incident notification",
        "body_lv": body_lv,
        "body_en": body_en,
        "locale": locale,
        "_via": "stub",
    }


def _stub_summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(events)
    statuses = [
        e.get("payload", {}).get("to") for e in events
        if e.get("type") == "status_changed"
    ]
    last = statuses[-1] if statuses else "unknown"
    parts = [f"Case progressed through {n} events with {len(statuses)} status changes."]
    if statuses:
        parts.append("Trajectory: " + " -> ".join(s or "open" for s in statuses) + ".")
    parts.append(f"Current state: {last}.")
    return {"summary": " ".join(parts), "event_count": n, "_via": "stub"}


def _stub_root_cause(text: str) -> dict[str, Any]:
    lo = (text or "").lower()
    return {
        "hypothesis": (
            "Probable hardware-layer failure on the affected device; "
            "needs operator validation against device logs."
            if ("link" in lo or "down" in lo) else
            "Insufficient evidence for automated root-cause inference."
        ),
        "evidence_keywords": [
            w for w in {"link", "down", "interface", "router", "switch",
                        "power", "disk", "latency"}
            if w in lo
        ],
        "confidence": 0.5,
        "_via": "stub",
    }
