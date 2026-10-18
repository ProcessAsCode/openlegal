"""End-to-end agent-layer test.

Drives the real planner loop with a scripted provider (no network), a real
Postgres and a real e-Līgumi store behind `uas.*`. Proves the four properties
the legal pilot depends on:

  * the planner chooses actions at runtime and the choices are recorded
    before they execute;
  * a read-only tool runs without a human;
  * an irreversible tool PARKS the run and a chat message does not open it;
  * approve executes exactly that action; reject halts the run.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OPENLEGAL_DB_URL", "postgresql+asyncpg://postgres@127.0.0.1:55432/openlegal")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from openlegal.agent import guardrails, tools as broker  # noqa: E402
from openlegal.db import session_scope  # noqa: E402
from openlegal.main import app  # noqa: E402
from openlegal.models.organization import Organization  # noqa: E402

ORG_SLUG = "demo-agent-test"

# One event loop for the whole module: the SQLAlchemy engine is a module-level
# singleton, so a per-test loop leaves its pool bound to a closed loop.
pytestmark = pytest.mark.asyncio(loop_scope="module")


class ScriptedProvider:
    """Stands in for the LLM: returns decisions from a list, in order."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []

    async def complete_json(self, system, user, *, max_tokens=1024):
        self.prompts.append(user)
        if not self.script:
            return {"thought": "nothing left", "action": None, "done": True, "answer": "done"}
        return self.script.pop(0)


@pytest.fixture(scope="module", autouse=True)
async def _dispose_engine_after_module():
    """The engine is a module-level singleton and this module pins one event
    loop. Dispose the pool afterwards so later test modules do not inherit
    connections bound to a loop that has closed."""
    yield
    from openlegal.db import dispose_engine
    await dispose_engine()


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    holder = {}

    def install(script):
        p = ScriptedProvider(script)
        monkeypatch.setattr("openlegal.llm.provider.complete_json", p.complete_json)
        monkeypatch.setattr("openlegal.llm.provider.enabled", lambda: True)
        monkeypatch.setattr("openlegal.llm.provider.model_ref", lambda: "scripted:test")
        holder["p"] = p
        return p

    holder["install"] = install
    yield holder


async def _org() -> None:
    async with session_scope() as s:
        from sqlalchemy import select
        row = (await s.execute(select(Organization).where(Organization.slug == ORG_SLUG))).scalar_one_or_none()
        if row is None:
            s.add(Organization(slug=ORG_SLUG, name="Demo (agent test)",
                               did="did:web:test.local:demo-agent-test"))


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       headers={"X-Org-Slug": ORG_SLUG}, timeout=30)


async def test_tool_catalogue_classifies_reversibility() -> None:
    await _org()
    async with _client() as c:
        r = await c.get("/api/agent/tools")
    assert r.status_code == 200
    by_name = {t["name"]: t for t in r.json()["tools"]}
    assert by_name["uas.read"]["reversibility"] == "read_only"
    assert by_name["register.sync"]["reversibility"] == "reversible"
    assert by_name["penalty.accrue"]["reversibility"] == "irreversible"
    # unknown capabilities fail safe
    assert broker.reversibility("something.new") == broker.IRREVERSIBLE


async def test_read_only_run_completes_without_human(_patch_provider) -> None:
    await _org()
    _patch_provider["install"]([
        {"thought": "list what the store holds", "action": "uas.list", "inputs": {},
         "scratchpad": {"phase": "survey"}, "done": False},
        {"thought": "enough for the summary", "action": None, "done": True,
         "answer": "Krātuvē nav līgumu; nav ko analizēt."},
    ])
    async with _client() as c:
        r = await c.post("/api/agent/runs", json={"goal": "Kādi līgumi ir krātuvē?"})
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "completed"
    acts = [s for s in run["steps"] if s["phase"] == "act"]
    assert acts and acts[0]["action_capability"] == "uas.list"
    assert acts[0]["guardrail_verdict"] == "allow"
    assert acts[0]["thought"]  # the reason is recorded, not just the effect
    assert run["outcome"]["answer"].startswith("Krātuvē")


async def test_irreversible_action_parks_and_chat_does_not_approve(_patch_provider) -> None:
    await _org()
    _patch_provider["install"]([
        {"thought": "the deadline is missed, propose a penalty", "action": "penalty.accrue",
         "inputs": {"contract_value": 10000, "days_late": 5}, "done": False},
        {"thought": "done", "action": None, "done": True, "answer": "Soda aprēķins sagatavots."},
    ])
    async with _client() as c:
        r = await c.post("/api/agent/runs", json={"goal": "Aprēķini kavējuma sodu par LIG-1"})
        run = r.json()
        assert run["status"] == "awaiting_approval"
        parked = [s for s in run["steps"] if s["guardrail_verdict"] == "require_approval"]
        assert len(parked) == 1 and parked[0]["action_capability"] == "penalty.accrue"
        assert parked[0]["observation"] is None  # it did NOT run

        # "ok" in the chat box must not be an approval path
        r = await c.post("/api/agent/chat", json={"run_id": run["id"], "message": "ok, dari"})
        after = r.json()
        assert after["status"] == "awaiting_approval"
        assert [s for s in after["steps"] if s["guardrail_verdict"] == "require_approval"][0]["observation"] is None
        assert any(m["is_interjection"] for m in after["messages"])

        r = await c.post(f"/api/agent/runs/{run['id']}/approve")
        approved = r.json()
        step = [s for s in approved["steps"] if s["action_capability"] == "penalty.accrue"][0]
        assert step["guardrail_verdict"] == "allow"
        assert step["approved_at"] is not None
        assert step["observation"] is not None  # now it ran
        assert approved["status"] == "completed"


async def test_reject_halts_the_run(_patch_provider) -> None:
    await _org()
    _patch_provider["install"]([
        {"thought": "notify the board", "action": "notify.alert",
         "inputs": {"message": "LIG-2 beidzas"}, "done": False},
    ])
    async with _client() as c:
        run = (await c.post("/api/agent/runs", json={"goal": "Brīdini par LIG-2"})).json()
        assert run["status"] == "awaiting_approval"
        r = await c.post(f"/api/agent/runs/{run['id']}/reject", json={"reason": "nav vajadzīgs"})
        out = r.json()
    assert out["status"] == "halted"
    assert "nav vajadzīgs" in out["halt_reason"]
    step = [s for s in out["steps"] if s["action_capability"] == "notify.alert"][0]
    assert step["guardrail_verdict"] == "deny"
    assert step["observation"] is None


async def test_budget_and_repetition_are_enforced(_patch_provider) -> None:
    await _org()
    same = {"thought": "look again", "action": "uas.list", "inputs": {}, "done": False}
    _patch_provider["install"]([dict(same) for _ in range(6)])
    async with _client() as c:
        run = (await c.post("/api/agent/runs", json={"goal": "cikls", "max_steps": 3})).json()
    assert run["status"] in ("halted", "completed")
    denies = [s for s in run["steps"] if s["guardrail_verdict"] == "deny"]
    assert any("repeated" in (s["guardrail_reason"] or "") or "budget" in (s["guardrail_reason"] or "")
               for s in denies)
    assert run["steps_used"] <= 3


async def test_capability_outside_allowlist_is_denied(_patch_provider) -> None:
    await _org()
    _patch_provider["install"]([
        {"thought": "send it", "action": "comm.send-email", "inputs": {"to": "x@y.lv"}, "done": False},
        {"thought": "give up", "action": None, "done": True, "answer": "nevaru"},
    ])
    async with _client() as c:
        run = (await c.post("/api/agent/runs", json={"goal": "sūti e-pastu",
                                                    "allowed_capabilities": ["uas.list", "uas.read"]})).json()
    step = [s for s in run["steps"] if s["action_capability"] == "comm.send-email"][0]
    assert step["guardrail_verdict"] == "deny"
    assert "allow-list" in step["guardrail_reason"]


def test_fingerprint_is_stable_across_key_order() -> None:
    a = guardrails.fingerprint("uas.read", {"id": 1, "version": 2})
    b = guardrails.fingerprint("uas.read", {"version": 2, "id": 1})
    assert a == b
