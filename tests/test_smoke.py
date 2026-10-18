"""Phase 0 smoke test: confirm the FastAPI app imports and /api/health works."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from openlegal.main import app


@pytest.mark.asyncio
async def test_health_endpoint_responds_ok() -> None:
    """The most basic check possible: the API is alive."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "openlegal"


@pytest.mark.asyncio
async def test_root_endpoint_returns_pointers() -> None:
    """The friendly root response should point at docs and health."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "OpenLegal"
    assert "/api/health" in body["health"]


@pytest.mark.asyncio
async def test_uapf_manifest_lists_planned_capabilities() -> None:
    """Engine discovers what this host can do via the manifest endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/uapf/host/manifest")
    assert response.status_code == 200
    body = response.json()
    capability_names = {c["name"] for c in body["capabilities"]}
    assert "ai.classify" in capability_names
    assert "incident.fetch" in capability_names
    # Legal-domain capabilities (contract and governance monitoring)
    for name in ("agreement.load", "governance.evaluate", "obligation.scan", "uas.read"):
        assert name in capability_names, name


# --- Phase 1: model registration check ---------------------------------------

def test_model_metadata_registers_all_tables() -> None:
    """All models are imported and registered with Base.metadata."""
    from openlegal.models import Base

    table_names = set(Base.metadata.tables.keys())
    expected = {
        "organizations",
        "users",
        "expert_groups",
        "expert_group_memberships",
        "connections",
        "taxonomy_nodes",
        "service_tiers",
        "signals",
        "cases",
        "case_events",
        "comments",
        "attachments",
        "ai_decisions",
        "dmn_evaluations",
        "vc_references",
        "uapf_executions",
        "uapf_capability_invocations",
        "audit_log",
        "uapf_sessions",
        "legal_agreements",
        "agent_runs",
        "agent_steps",
        "agent_messages",
    }
    missing = expected - table_names
    assert not missing, f"missing tables: {missing}"
    unexpected = table_names - expected
    assert not unexpected, f"unexpected tables (add them to this test): {unexpected}"


def test_case_status_enum_has_expected_values() -> None:
    """Spot-check one of the central enums."""
    from openlegal.models import CaseStatus

    assert CaseStatus.OPEN == "open"
    assert CaseStatus.CLOSED == "closed"
    assert {s.value for s in CaseStatus} >= {
        "open", "triaged", "in_progress", "resolved", "closed"
    }
