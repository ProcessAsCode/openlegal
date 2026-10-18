"""Demo-data seeder.

Creates one Organization, seven ExpertGroups, three ServiceTiers, twelve
TaxonomyNodes, and ~10 realistic Cases at various lifecycle stages. Each
seeded case starts as a Signal that goes through the same inline-triage
runner real intake uses, so the timeline + AIDecisions + DMNEvaluations
look identical to what a live visitor would produce.

Idempotent: if the demo org already exists, `seed()` is a no-op. Use
`reset_and_seed()` (or POST /api/admin/reset) to wipe and reseed.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import session_scope
from openlegal.models.case import CaseStatus
from openlegal.models.expert_group import ExpertGroup
from openlegal.models.organization import Organization
from openlegal.models.taxonomy import ServiceTier
from openlegal.models.signal import Signal, SignalSource, SignalStatus
from openlegal.models.taxonomy import TaxonomyNode
from openlegal.services.incident import (
    open_case_from_signal,
    transition_case,
)
from openlegal.services.triage import run_triage_inline


DEMO_ORG_SLUG = "demo"


# ---------------------------------------------------------------------------
# Resource definitions
# ---------------------------------------------------------------------------

EXPERT_GROUPS = [
    ("helpdesk-l1",      "L1 helpdesk",          1, "First-line operator triage."),
    ("noc-l1",           "Network Ops L1",       1, "Network monitoring + first-line response."),
    ("noc-l2",           "Network Ops L2",       2, "Network engineering, on-call for P1."),
    ("soc-l2",           "Security Ops L2",      2, "Security incident response, 24/7."),
    ("facility-l2",      "Facility & Power L2",  2, "Data-center facility, power, environment."),
    ("platform-l2",      "Platform Ops L2",      2, "Platform / storage / virtualization."),
    ("external-handoff", "External handoff",     1, "Cases transferred outside the org."),
]

SERVICE_TIERS = [
    ("tier_1",      "Tier 1 (highest)",  "Mission-critical services with strict SLAs.", 15,   240),
    ("tier_2",      "Tier 2",            "Standard production services.",                60,   480),
    ("best_effort", "Best effort",       "Non-SLA services.",                            None, None),
]

TAXONOMY = [
    ("network",                   "Tīkls",                 "Network"),
    ("network.outage",            "Tīkla pārtraukums",     "Network outage"),
    ("network.outage.link_down",  "Saites pārtraukums",    "Link down"),
    ("network.degradation",       "Tīkla degradācija",     "Network degradation"),
    ("network.routing",           "Maršrutēšana",          "Routing"),
    ("network.dns",               "DNS",                   "DNS"),
    ("security",                  "Drošība",               "Security"),
    ("security.incident",         "Drošības incidents",    "Security incident"),
    ("facility.power",            "Elektroapgāde",         "Power / facility"),
    ("storage.capacity",          "Diska vieta",           "Storage capacity"),
    ("service.customer_request",  "Klienta pieprasījums",  "Customer request"),
    ("unknown.uncategorized",     "Neklasificēts",         "Uncategorized"),
]


# ---------------------------------------------------------------------------
# Sample scenarios — each becomes one signal -> case -> triage -> optional
# additional transitions and comments
# ---------------------------------------------------------------------------

# Each scenario:
#   source            : SignalSource value
#   external_id       : adapter event id
#   raw_payload       : adapter-shaped dict
#   final_status      : where the case should end up (open|triaged|in_progress|
#                       waiting_customer|resolved|closed)
#   age_minutes       : how long ago the signal was received (so the queue
#                       has a believable distribution of ages)

SCENARIOS: list[dict[str, Any]] = [
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9342",
        "raw_payload": {
            "title": "Link down on edge router rtr-r1",
            "host": "rtr-r1.demo.example",
            "severity": "high",
            "body": "Interface ge-0/0/3 went DOWN at 09:14:02 UTC. BGP session to upstream provider AS6939 also flapping.",
            "event_id": "9342",
            "tags": ["network", "edge"],
        },
        "final_status": "in_progress",
        "age_minutes": 18,
    },
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9351",
        "raw_payload": {
            "title": "BGP session flapping rtr-core-02 → AS6939",
            "host": "rtr-core-02.demo.example",
            "severity": "high",
            "body": "BGP peer 198.51.100.1 toggled UP/DOWN 7 times in 12 minutes. Adj-RIB-In count unstable.",
            "tags": ["network", "bgp"],
        },
        "final_status": "triaged",
        "age_minutes": 35,
    },
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9374",
        "raw_payload": {
            "title": "DDoS attack pattern detected on edge",
            "host": "rtr-r3.demo.example",
            "severity": "critical",
            "body": "Volumetric UDP flood, 4.2 Gbps inbound to 192.0.2.0/24. Source: 12 ASNs, predominantly AS197207. Auto-mitigation engaged.",
            "tags": ["security", "ddos"],
        },
        "final_status": "in_progress",
        "age_minutes": 7,
    },
    {
        "source": SignalSource.EMAIL,
        "external_id": "MSG-2026-05-25-001",
        "raw_payload": {
            "subject": "Klients SIA Latvija Tev: lūgums palielināt joslas platumu",
            "from": "ivars.berzins@klients-latvija.lv",
            "to": "atbalsts@demo.example",
            "body": "Labdien, mūsu uzņēmumam nepieciešams palielināt internet pieslēguma joslas platumu no 100 Mbps uz 500 Mbps. Lūdzu, informējiet par procedūru un izmaksām. Ar cieņu, Ivars Bērziņš",
        },
        "final_status": "open",
        "age_minutes": 4,
    },
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9301",
        "raw_payload": {
            "title": "UPS battery degraded — DC-Riga rack B7",
            "host": "ups-b7.demo.example",
            "severity": "average",
            "body": "Battery health check returned 67% (threshold 80%). Last replaced 2021-09; recommended replacement before next planned maintenance window.",
            "tags": ["facility", "power"],
        },
        "final_status": "waiting_customer",
        "age_minutes": 240,
    },
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9288",
        "raw_payload": {
            "title": "Disk space critical on mon-aggr-01",
            "host": "mon-aggr-01.demo.example",
            "severity": "high",
            "body": "/var/lib/elasticsearch at 94% (8.7 TB of 9.3 TB). Index retention policy may have drifted; investigate before logs start dropping.",
        },
        "final_status": "resolved",
        "age_minutes": 1080,
    },
    {
        "source": SignalSource.JIRA_DC,
        "external_id": "OPS-1247",
        "raw_payload": {
            "key": "OPS-1247",
            "fields": {
                "summary": "Slow downloads reported by customer KS-1029",
                "description": "Customer Ltd. Kurzemes Sakari reports speeds of ~12 Mbps on 100 Mbps line during evenings. Looks like CGNAT pool saturation.",
                "priority": {"name": "Average"},
                "status": {"name": "Open"},
                "components": [{"name": "Network"}, {"name": "Customer"}],
            },
        },
        "final_status": "triaged",
        "age_minutes": 90,
    },
    {
        "source": SignalSource.ZABBIX,
        "external_id": "ZBX-EVT-9099",
        "raw_payload": {
            "title": "DNS resolution latency spike — dns-anycast-01",
            "host": "dns-anycast-01.demo.example",
            "severity": "warning",
            "body": "p95 query latency rose from 8ms to 240ms over the last 6 minutes. Recursive resolver only; authoritative unaffected.",
        },
        "final_status": "closed",
        "age_minutes": 2880,
    },
    {
        "source": SignalSource.MANUAL,
        "external_id": None,
        "raw_payload": {
            "title": "Planota tehniska apkope - rtr-r2 sektors",
            "description": "Plānota apkope 2026-05-27 02:00-04:00 EET. Klients ir informēts. Sagaidāms īss pārtraukums.",
            "host": "rtr-r2.demo.example",
            "tags": ["planned", "maintenance"],
        },
        "final_status": "open",
        "age_minutes": 30,
    },
    {
        "source": SignalSource.EMAIL,
        "external_id": "MSG-2026-05-25-002",
        "raw_payload": {
            "subject": "Suspicious login attempts on infra portal",
            "from": "security-monitor@demo.example",
            "to": "soc@demo.example",
            "body": "47 failed admin login attempts in 8 minutes from 5 distinct IPs. User account 'mzariņš'. Rate-limit engaged automatically; investigation recommended.",
        },
        "final_status": "in_progress",
        "age_minutes": 22,
    },
]


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def seed_resources(session: AsyncSession) -> Organization:
    """Seed org + expert groups + service tiers + taxonomy.

    Returns the demo org. Idempotent on the org check (won't duplicate).
    """
    # Org
    stmt = select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if org is None:
        org = Organization(
            slug=DEMO_ORG_SLUG,
            name="Demo organisation",
            did=f"did:web:openlegal.algomation.io:{DEMO_ORG_SLUG}",
            default_locale="lv",
        )
        session.add(org)
        await session.flush()

    # Expert groups
    for slug, name, level, desc in EXPERT_GROUPS:
        stmt = select(ExpertGroup).where(
            ExpertGroup.org_id == org.id, ExpertGroup.slug == slug,
        )
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            session.add(ExpertGroup(
                org_id=org.id, slug=slug, name=name, level=level,
                description=desc,
            ))

    # Service tiers
    for code, name, desc, first_min, res_min in SERVICE_TIERS:
        stmt = select(ServiceTier).where(
            ServiceTier.org_id == org.id, ServiceTier.code == code,
        )
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            session.add(ServiceTier(
                org_id=org.id, code=code, name=name, description=desc,
                sla_first_response_minutes=first_min,
                sla_resolution_minutes=res_min,
            ))

    # Taxonomy
    for code, label_lv, label_en in TAXONOMY:
        stmt = select(TaxonomyNode).where(
            TaxonomyNode.org_id == org.id, TaxonomyNode.code == code,
        )
        if (await session.execute(stmt)).scalar_one_or_none() is None:
            session.add(TaxonomyNode(
                org_id=org.id, code=code,
                label_lv=label_lv, label_en=label_en,
            ))

    await session.flush()
    return org


async def seed_scenarios(session: AsyncSession, org: Organization) -> list[uuid.UUID]:
    """Open one case per scenario, run inline triage, transition to final state.

    Returns list of created case ids.
    """
    case_ids: list[uuid.UUID] = []
    now = datetime.now(timezone.utc)

    for sc in SCENARIOS:
        received_at = now - timedelta(minutes=sc["age_minutes"])

        signal = Signal(
            org_id=org.id,
            source=sc["source"],
            external_id=sc["external_id"],
            raw_payload=sc["raw_payload"],
            received_at=received_at,
            status=SignalStatus.RECEIVED,
        )
        session.add(signal)
        await session.flush()

        title = (
            sc["raw_payload"].get("title")
            or sc["raw_payload"].get("subject")
            or sc["raw_payload"].get("fields", {}).get("summary")
            or f"[{sc['source'].value}] event"
        )[:512]
        description = (
            sc["raw_payload"].get("body")
            or sc["raw_payload"].get("description")
            or sc["raw_payload"].get("fields", {}).get("description")
        )

        case = await open_case_from_signal(
            session, org=org, signal=signal,
            title=title, description=description,
            actor_label=f"seed/{sc['source'].value}",
        )
        await session.flush()

        # Backdate the case so the queue shows realistic ages
        case.opened_at = received_at
        case.created_at = received_at
        await session.flush()

        final = sc["final_status"]

        # Run inline triage UNLESS the scenario wants the case to stay
        # at 'open' (i.e. untriaged). The FSM is open -> triaged -> ..., so
        # once triaged a case cannot go back to open.
        if final != "open":
            await run_triage_inline(session, org, signal=signal, case=case)
            await session.flush()

        # Walk further legal transitions for statuses past triaged.
        if final not in {"open", "triaged"}:
            chain = _transition_chain_to(final)
            for step in chain:
                await transition_case(
                    session, case, to_status=CaseStatus(step),
                    reason=f"Demo seed: progress to {step}",
                    actor_label="seed/operator",
                )
                await session.flush()

        case_ids.append(case.id)

    return case_ids


def _transition_chain_to(final: str) -> list[str]:
    """Legal FSM chain from triaged to `final`. Mirrors services/incident.py."""
    if final == "triaged":
        return []
    if final == "in_progress":
        return ["in_progress"]
    if final == "waiting_customer":
        return ["in_progress", "waiting_customer"]
    if final == "waiting_third_party":
        return ["in_progress", "waiting_third_party"]
    if final == "resolved":
        return ["in_progress", "resolved"]
    if final == "closed":
        return ["in_progress", "resolved", "closed"]
    if final == "cancelled":
        return ["cancelled"]
    return []


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

async def seed_if_empty() -> dict[str, Any]:
    """Seed only if the demo org doesn't yet exist. Idempotent."""
    async with session_scope() as session:
        stmt = select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            n = await seed_uas_register(session, existing)
            return {"status": "skipped", "reason": "demo org already exists",
                    "uas_register_upserts": n}

        org = await seed_resources(session)
        case_ids = await seed_scenarios(session, org)
        uas_n = await seed_uas_register(session, org)
        return {
            "status": "seeded",
            "org_id": str(org.id),
            "org_slug": org.slug,
            "case_count": len(case_ids),
            "uas_register_upserts": uas_n,
        }


async def reset_and_seed() -> dict[str, Any]:
    """Truncate all tenant data, then run the full seed."""
    async with session_scope() as session:
        await session.execute(text(
            "TRUNCATE TABLE "
            "audit_log, uapf_capability_invocations, uapf_executions, "
            "attachments, comments, dmn_evaluations, case_events, "
            "ai_decisions, vc_references, signals, cases, "
            "service_tiers, taxonomy_nodes, connections, "
            "expert_group_memberships, expert_groups, users, organizations "
            "CASCADE"
        ))
        await session.commit()

    async with session_scope() as session:
        org = await seed_resources(session)
        case_ids = await seed_scenarios(session, org)
        uas_n = await seed_uas_register(session, org)
        return {
            "status": "reset_and_seeded",
            "org_id": str(org.id),
            "org_slug": org.slug,
            "case_count": len(case_ids),
            "uas_register_upserts": uas_n,
        }


__all__ = ["DEMO_ORG_SLUG", "seed_if_empty", "reset_and_seed"]

UAS_SAMPLES_DIRS = [Path("/app/seed/uas-samples"), Path("seed/uas-samples")]


async def seed_uas_register(session: AsyncSession, org: Organization) -> int:
    """Idempotently upsert sample UAS documents into the Agreement Register."""
    from openlegal.models.legal_agreement import AgreementStatus, LegalAgreement
    src = next((d for d in UAS_SAMPLES_DIRS if d.exists()), None)
    if src is None:
        return 0
    n = 0
    for f in sorted(src.glob("*.uas.json")):
        uas = json.loads(f.read_text(encoding="utf-8"))
        aid = uas.get("id")
        if not aid:
            continue
        stmt = select(LegalAgreement).where(LegalAgreement.org_id == org.id,
                                            LegalAgreement.agreement_id == aid)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = LegalAgreement(org_id=org.id, agreement_id=aid)
            session.add(row)
        prov = uas.get("provenance") or {}
        row.title = uas.get("title") or aid
        row.status = AgreementStatus.ACTIVE
        row.source_docus_id = prov.get("docus_id") or prov.get("docus_record")
        row.source_sap_id = prov.get("sap_contract_id")
        row.uas = uas
        n += 1
    return n
