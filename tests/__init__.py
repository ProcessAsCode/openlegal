"""OpenLegal test suite.

Layout (Phase 1):
  tests/
    unit/               # Pure function tests
    integration/        # API endpoint tests against a real DB (testcontainers)
    e2e/                # Full intake → triage → case → outbound flow
    fixtures/           # Sample Zabbix/Jira/email payloads
    conftest.py         # Shared fixtures

For Phase 0, only the smoke test exists — it confirms the FastAPI app
imports cleanly and `/api/health` responds.
"""
