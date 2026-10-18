"""End-to-end test of the intake + incidents API against a real Postgres.

This test does not use the pytest fixture pattern from Phase 0 because the
database connection happens at import time via `openlegal.db.get_engine()`.
The test:
  1. Overrides the global engine to point at the test Postgres
  2. Seeds an Organization row
  3. Drives the full intake → case → transition flow via httpx ASGITransport
  4. Asserts schema invariants at each step
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Override settings BEFORE importing the app
os.environ["OPENLEGAL_DB_URL"] = "postgresql+asyncpg://postgres@127.0.0.1:55432/openlegal"

from openlegal.db import set_engine_for_testing, get_session_factory  # noqa: E402
from openlegal.main import app  # noqa: E402
from openlegal.models.organization import Organization  # noqa: E402


ORG_SLUG = "demoop"


async def reset_db() -> None:
    """Truncate the data tables but keep the schema. Idempotent."""
    factory = get_session_factory()
    async with factory() as session:
        # Truncate in dependency-safe order via CASCADE.
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


async def seed_org() -> uuid.UUID:
    factory = get_session_factory()
    async with factory() as session:
        org = Organization(
            slug=ORG_SLUG,
            name="Demo Operator",
            did=f"did:web:openlegal.local:{ORG_SLUG}",
            default_locale="lv",
        )
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return org.id


async def main() -> None:
    engine = create_async_engine(os.environ["OPENLEGAL_DB_URL"])
    set_engine_for_testing(engine)

    print("== reset db ==")
    await reset_db()

    print("== seed org ==")
    org_id = await seed_org()
    print(f"   org_id = {org_id}")

    headers = {"X-Org-Slug": ORG_SLUG}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    ) as client:
        # --- POST /intake/ ----------------------------------------------------
        print("\n== POST /api/intake/ ==")
        payload = {
            "source": "zabbix",
            "external_id": "EVENT_98765",
            "raw_payload": {
                "title": "Link down on edge router rtr-r1",
                "host": "rtr-r1.example.net",
                "severity": "high",
                "body": "Interface ge-0/0/3 went DOWN at 09:14:02 UTC",
            },
            "dedupe_hash": "rtr-r1-link-down",
        }
        r = await client.post("/api/intake/", json=payload)
        assert r.status_code == 201, (r.status_code, r.text)
        sig = r.json()
        print(f"   signal_id   = {sig['id']}")
        print(f"   status      = {sig['status']}")
        print(f"   case_id     = {sig['case_id']}")
        assert sig["status"] == "opened_case"
        assert sig["case_id"] is not None
        case_id = sig["case_id"]

        # --- GET /incidents/ -------------------------------------------------
        print("\n== GET /api/incidents/ ==")
        r = await client.get("/api/incidents/")
        assert r.status_code == 200, r.text
        cases = r.json()
        assert len(cases) == 1
        case_summary = cases[0]
        print(f"   case_number = {case_summary['case_number']}")
        print(f"   status      = {case_summary['status']}")
        print(f"   title       = {case_summary['title']}")
        assert case_summary["status"] == "open"
        assert case_summary["case_number"].startswith("DEMOOP-")
        assert "Link down" in case_summary["title"]

        # --- GET /incidents/{id} ---------------------------------------------
        print(f"\n== GET /api/incidents/{case_id} ==")
        r = await client.get(f"/api/incidents/{case_id}")
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["id"] == case_id
        assert detail["status"] == "open"
        print(f"   description = {detail['description'][:60]!r}...")

        # --- POST /incidents/{id}/transition (illegal) -----------------------
        print("\n== POST .../transition (open -> resolved: ILLEGAL) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "resolved"},
        )
        assert r.status_code == 409, (r.status_code, r.text)
        print(f"   correctly rejected: {r.json()['detail'][:80]}...")

        # --- POST /incidents/{id}/transition (legal: open -> triaged) --------
        print("\n== POST .../transition (open -> triaged) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "triaged", "reason": "Network team paged"},
        )
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["status"] == "triaged"
        assert detail["triaged_at"] is not None
        print(f"   status      = {detail['status']}")
        print(f"   triaged_at  = {detail['triaged_at']}")

        # --- POST .../transition (triaged -> in_progress) --------------------
        print("\n== POST .../transition (triaged -> in_progress) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "in_progress"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

        # --- POST .../transition (in_progress -> resolved) -------------------
        print("\n== POST .../transition (in_progress -> resolved) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "resolved"},
        )
        assert r.status_code == 200
        detail = r.json()
        assert detail["status"] == "resolved"
        assert detail["resolved_at"] is not None

        # --- POST .../transition (resolved -> closed) ------------------------
        print("\n== POST .../transition (resolved -> closed) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "closed"},
        )
        assert r.status_code == 200
        detail = r.json()
        assert detail["status"] == "closed"
        assert detail["closed_at"] is not None

        # --- POST .../transition (closed -> open: ILLEGAL, terminal) ---------
        print("\n== POST .../transition (closed -> open: ILLEGAL, terminal) ==")
        r = await client.post(
            f"/api/incidents/{case_id}/transition",
            json={"to_status": "open"},
        )
        assert r.status_code == 409

        # --- GET .../events --------------------------------------------------
        print(f"\n== GET /api/incidents/{case_id}/events ==")
        r = await client.get(f"/api/incidents/{case_id}/events")
        assert r.status_code == 200, r.text
        events = r.json()
        print(f"   {len(events)} events:")
        for e in events:
            payload = e['payload']
            extra = ""
            if e["type"] == "status_changed":
                extra = f"  {payload.get('from')} -> {payload.get('to')}"
            print(f"     {e['type']:20s}{extra}")
        # Expect: signal_attached, status_changed(None->open), status_changed(open->triaged),
        # status_changed(triaged->in_progress), status_changed(in_progress->resolved),
        # status_changed(resolved->closed)
        assert len(events) == 6, f"expected 6 events, got {len(events)}"
        types = [e["type"] for e in events]
        assert types[0] == "signal_attached"
        assert types[1:] == ["status_changed"] * 5

        # --- POST a SECOND signal to verify case_number sequence -------------
        print("\n== POST /api/intake/ (second signal) ==")
        r = await client.post("/api/intake/", json={
            "source": "email",
            "raw_payload": {"subject": "Customer X reports slow downloads", "body": "blah"},
        })
        assert r.status_code == 201, r.text
        second_sig = r.json()
        r2 = await client.get(f"/api/incidents/{second_sig['case_id']}")
        assert r2.status_code == 200
        second_case = r2.json()
        print(f"   second case_number = {second_case['case_number']}")
        first_case_seq = int(case_summary["case_number"].split("-")[-1])
        second_case_seq = int(second_case["case_number"].split("-")[-1])
        assert second_case_seq == first_case_seq + 1

        # --- Filter: list open only ------------------------------------------
        print("\n== GET /api/incidents/?status=open ==")
        r = await client.get("/api/incidents/?status=open")
        assert r.status_code == 200
        only_open = r.json()
        print(f"   {len(only_open)} open cases")
        assert len(only_open) == 1
        assert only_open[0]["case_number"] == second_case["case_number"]

        # --- Manual create ---------------------------------------------------
        print("\n== POST /api/incidents/ (manual create) ==")
        r = await client.post("/api/incidents/", json={
            "title": "Manually-opened test ticket",
            "description": "Operator dialed in",
            "priority": "P3",
        })
        assert r.status_code == 201, r.text
        manual = r.json()
        print(f"   manual case_number = {manual['case_number']}")
        print(f"   priority           = {manual['priority']}")
        assert manual["priority"] == "P3"
        assert int(manual["case_number"].split("-")[-1]) == first_case_seq + 2

        # --- 404 path --------------------------------------------------------
        print("\n== GET /api/incidents/<bogus> ==")
        r = await client.get(f"/api/incidents/{uuid.uuid4()}")
        assert r.status_code == 404

        # --- Header missing --------------------------------------------------
        print("\n== GET /api/incidents/ without X-Org-Slug ==")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as no_org:
            r = await no_org.get("/api/incidents/")
            assert r.status_code == 400, r.text
            print(f"   correctly rejected: {r.json()['detail']}")

    await engine.dispose()
    print("\n== ALL ASSERTIONS PASSED ==")


if __name__ == "__main__":
    asyncio.run(main())
