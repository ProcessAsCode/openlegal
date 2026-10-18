"""Versioned prompts for OpenLegal AI capabilities.

Keep prompts short, instructive, and JSON-output-shaped. The handlers in
uapf/handlers/ai.py record the prompt hash on each AIDecision so the
exact wording that produced a decision can be reconstructed for audit.
"""

from __future__ import annotations


# Taxonomy codes the classifier may emit. Mirrors
# uapf-packages/lv.itsm.incident.triage/bindings/resources.yaml.
TAXONOMY_CODES = [
    "network.outage.link_down",
    "network.degradation",
    "network.routing",
    "network.dns",
    "security.incident",
    "facility.power",
    "storage.capacity",
    "service.customer_request",
    "unknown.uncategorized",
]


SYSTEM_BASE = (
    "You are an incident-triage assistant for a critical-infrastructure "
    "ITSM . You always respond with strictly valid JSON, no "
    "prose, no Markdown fences."
)


def classify_system() -> str:
    codes = ", ".join(TAXONOMY_CODES)
    return (
        f"{SYSTEM_BASE}\n\n"
        f"Pick exactly one taxonomy code from this list: {codes}. "
        f"Return JSON of shape "
        f'{{"taxonomy_code": "<code>", "confidence": <0.0..1.0>, '
        f'"reasoning": "<one-sentence justification in English>"}}.'
    )


def classify_user(text: str) -> str:
    return f"Incident text:\n---\n{text}\n---\nClassify it."


def suggest_priority_system() -> str:
    return (
        f"{SYSTEM_BASE}\n\n"
        "Suggest a priority for the incident on the P1..P4 scale. "
        "P1=disaster/critical/security-incident, P2=high, P3=warning/average, "
        "P4=low/info. Service-tier 1 escalates one level (high+tier_1 -> P1). "
        "Return JSON: "
        '{"priority": "P1|P2|P3|P4", "reason": "<one-sentence justification>"}.'
    )


def suggest_priority_user(
    severity: str, service_tier: str, classification: str,
) -> str:
    return (
        f"severity={severity!r}, service_tier={service_tier!r}, "
        f"classification={classification!r}"
    )


def draft_response_system(org_slug: str) -> str:
    return (
        f"{SYSTEM_BASE}\n\n"
        f"Draft a customer-facing incident notification in both the customer's preferred language and "
        f"English, on behalf of {org_slug.upper()}. The customer has reported "
        f"or been affected by the issue. Tone: professional, calm, factual; "
        f"acknowledge the problem, state that the team is investigating, give "
        f"an ETA if provided. Do NOT promise specific resolutions. Use proper "
        f"the customer's native diacritics. Keep each body under 90 words.\n\n"
        f"Return JSON of shape: "
        f'{{"subject_lv": "...", "subject_en": "...", '
        f'"body_lv": "...", "body_en": "..."}}.'
    )


def draft_response_user(
    what_happened: str, eta_minutes: int | None,
) -> str:
    eta_line = f"ETA: {eta_minutes} minutes." if eta_minutes else "ETA: not yet known."
    return f"Incident: {what_happened}\n{eta_line}"


def summarize_timeline_system() -> str:
    return (
        f"{SYSTEM_BASE}\n\n"
        "Summarize the case timeline in 2-3 plain English sentences. "
        "Lead with the trajectory (statuses + key transitions), end with the "
        "current state. Return JSON: "
        '{"summary": "<2-3 sentences>", "event_count": <int>}.'
    )


def summarize_timeline_user(events: list[dict]) -> str:
    import json
    return f"Events (chronological):\n{json.dumps(events, ensure_ascii=False)[:4000]}"


def extract_root_cause_system() -> str:
    return (
        f"{SYSTEM_BASE}\n\n"
        "From the artifacts below, propose a single most-likely root-cause "
        "hypothesis and list keywords that support it. Be conservative: if "
        "evidence is weak, say so. Return JSON: "
        '{"hypothesis": "<one paragraph>", '
        '"evidence_keywords": ["<word>", ...], '
        '"confidence": <0.0..1.0>}.'
    )


def extract_root_cause_user(text: str) -> str:
    return f"Artifacts:\n---\n{text[:4000]}\n---"
