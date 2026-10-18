"""UAPF host capability manifest.

Single source of truth for which capabilities this host advertises and which
handler function satisfies each. The HTTP `/uapf/host/manifest` endpoint
derives from this; the dispatcher uses this to route incoming capability calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.organization import Organization


CapabilityHandler = Callable[
    [AsyncSession, Organization, dict[str, Any], dict[str, Any]],
    Awaitable[dict[str, Any]],
]


@dataclass(frozen=True)
class CapabilityDescriptor:
    name: str
    version: str
    summary: str
    handler: CapabilityHandler


def _registry() -> dict[str, CapabilityDescriptor]:
    from openlegal.uapf.handlers import agreement, ai, comm, data, incident, intake, legal, mip, uas

    descriptors = [
        CapabilityDescriptor("uas.list", "1",
            "List agreements held in the e-Līgumi UAS store (read-only systems connector).",
            uas.uas_list),
        CapabilityDescriptor("uas.read", "1",
            "Read one agreement (parsed UAS + version) from the e-Līgumi store (read-only).",
            uas.uas_read),
        CapabilityDescriptor("register.sync", "1",
            "Mirror one store agreement into the Agreement Register as a derived view.",
            uas.register_sync),
        CapabilityDescriptor("agreement.load", "1",
            "Load a UAS agreement co-versioned in the package.",
            agreement.load_agreement),
        CapabilityDescriptor("obligation.scan", "1",
            "Scan a UAS agreement into per-obligation states.",
            agreement.scan_obligations),
        CapabilityDescriptor("ai.classify_clause", "1",
            "Classify free-text agreement clauses into obligation types.",
            ai.classify_clause),
        CapabilityDescriptor("penalty.accrue", "1",
            "Compute a capped late-performance penalty (proposed claim).",
            agreement.penalty_accrue),
        CapabilityDescriptor("event.schedule", "1",
            "Record a scheduled monitoring tick.",
            agreement.event_schedule),
        CapabilityDescriptor("docus.read", "1",
            "Read contract registry metadata from DOCUS (mock adapter in v0.1).",
            legal.docus_read),
        CapabilityDescriptor("sap.read_actuals", "1",
            "Read actual spend / payments per contract from SAP (mock adapter in v0.1).",
            legal.sap_read_actuals),
        CapabilityDescriptor("governance.evaluate", "1",
            "Evaluate the corporate competence matrix: required approvals for a value.",
            legal.governance_evaluate),
        CapabilityDescriptor("schedule.compute_chain", "1",
            "Compute the approval-chain critical path through the governance calendar.",
            legal.schedule_compute_chain),
        CapabilityDescriptor("notify.alert", "1",
            "Record a governance alert to the obligations board channel.",
            legal.notify_alert),
        CapabilityDescriptor("mip.resolve_classification", "1",
            "Report a stored object's Microsoft Purview sensitivity label and "
            "protection state (read-only; mock adapter in v0.1).",
            mip.resolve_classification),
        CapabilityDescriptor("mip.read_protected", "1",
            "Return extracted plaintext of a protected object without removing "
            "its label; decrypt happens in-tenant, access is audited (mock in v0.1).",
            mip.read_protected),
        CapabilityDescriptor("incident.fetch", "1",
            "Read a case by id; returns the full case detail snapshot.",
            incident.fetch),
        CapabilityDescriptor("incident.update", "1",
            "Apply a typed patch to a case (status, priority, assignment, ...).",
            incident.update),
        CapabilityDescriptor("intake.normalize", "1",
            "Normalize a raw adapter payload into the OpenLegal signal schema.",
            intake.normalize),
        CapabilityDescriptor("ai.classify", "1",
            "Classify an incident into the org's taxonomy.",
            ai.classify),
        CapabilityDescriptor("ai.suggest-priority", "1",
            "Suggest P1-P4 priority from incident text and service tier.",
            ai.suggest_priority),
        CapabilityDescriptor("ai.draft-response", "1",
            "Draft a customer-facing reply for operator review.",
            ai.draft_response),
        CapabilityDescriptor("ai.summarize-timeline", "1",
            "Produce a short narrative summary of the case timeline.",
            ai.summarize_timeline),
        CapabilityDescriptor("ai.extract-root-cause", "1",
            "Extract a structured root-cause hypothesis from incident artifacts.",
            ai.extract_root_cause),
        CapabilityDescriptor("data.write", "1",
            "Merge a JSON patch into a case's state_snapshot.",
            data.write),
        CapabilityDescriptor("event.emit", "1",
            "Append a typed event to the case timeline.",
            data.event_emit),
        CapabilityDescriptor("dmn.evaluate", "1",
            "Evaluate a DMN decision table by id; returns matched rules + output.",
            data.dmn_evaluate),
        CapabilityDescriptor("comm.send-email", "1",
            "Send a customer-facing email reply (Phase 1: stub).",
            comm.send_email),
        CapabilityDescriptor("comm.add-comment", "1",
            "Add an internal note or customer-facing comment to a case.",
            comm.add_comment),
    ]
    return {d.name: d for d in descriptors}


_CACHED: dict[str, CapabilityDescriptor] | None = None


def get_registry() -> dict[str, CapabilityDescriptor]:
    global _CACHED
    if _CACHED is None:
        _CACHED = _registry()
    return _CACHED


def get_handler(name: str) -> CapabilityDescriptor | None:
    return get_registry().get(name)


def manifest_dict(host_did: str, base_url: str) -> dict[str, Any]:
    return {
        "host_did": host_did,
        "host_base_url": base_url,
        "uapf_ip_version": "0.1",
        "capabilities": [
            {
                "name": d.name,
                "version": d.version,
                "summary": d.summary,
                "status": "available",
            }
            for d in get_registry().values()
        ],
    }


__all__ = [
    "CapabilityDescriptor", "CapabilityHandler",
    "get_handler", "get_registry", "manifest_dict",
]
