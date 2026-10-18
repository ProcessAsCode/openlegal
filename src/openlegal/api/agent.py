"""Agent API — start runs, watch them, approve or reject parked actions, talk.

This is the oversight surface. Approval is explicit: a chat message sent
while an action is parked is queued as an interjection and the gate stays
shut — "ok" in the chat box is never an approval path.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.deps import get_current_org
from openlegal.models.agent import AgentRunStatus
from openlegal.models.organization import Organization

router = APIRouter()


class RunCreate(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)
    agreement_ref: str | None = None
    allowed_capabilities: list[str] | None = None
    max_steps: int | None = Field(default=None, ge=1, le=40)


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    run_id: uuid.UUID | None = None
    agreement_ref: str | None = None


@router.get("/tools", summary="Tool catalogue the planner may choose from")
async def tools_catalogue() -> dict[str, Any]:
    from openlegal.agent import guardrails, tools
    cat = tools.catalogue()
    return {"tools": cat, "policy": guardrails.policy_summary(12, [t["name"] for t in cat])}


@router.get("/runtime", summary="Runtime configuration: model, store, limits (no secrets)")
async def runtime_config() -> dict[str, Any]:
    """What a supervisor needs to be able to see without shell access: which
    model answers, where it runs, whether the agreement store is reachable.
    Deliberately returns no key material — only shape and reachability."""
    import httpx

    from openlegal.agent import tools as broker
    from openlegal.core.config import settings
    from openlegal.llm import provider

    store: dict[str, Any] = {"base_url": settings.ELIGUMI_BASE_URL, "reachable": False,
                             "agreements": None, "detail": ""}
    try:
        headers = {"x-api-key": settings.ELIGUMI_API_KEY} if settings.ELIGUMI_API_KEY else {}
        async with httpx.AsyncClient(timeout=5, headers=headers) as c:
            r = await c.get(f"{settings.ELIGUMI_BASE_URL.rstrip('/')}/api/agreements")
        if r.status_code == 200:
            store.update(reachable=True, agreements=r.json().get("count", 0), detail="ok")
        else:
            store["detail"] = f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        store["detail"] = type(exc).__name__

    note = ("Smilškastes vidē nodrošinātājam jābūt openai_compat ar galapunktu uz "
            "anonimizācijas vārteju; neviens pieprasījums neaiziet uz publisku modeļa "
            "pakalpojumu.")
    return {
        "llm": {"provider": settings.LLM_PROVIDER, "model": settings.LLM_MODEL,
                "endpoint": settings.LLM_ENDPOINT, "configured": provider.enabled(), "note": note},
        "store": store,
        "agent": {"max_steps": settings.AGENT_MAX_STEPS,
                  "irreversible": [t["name"] for t in broker.catalogue()
                                   if t["reversibility"] == broker.IRREVERSIBLE]},
    }


@router.post("/runs", status_code=201, summary="Start an agent run")
async def create_run(body: RunCreate, org: Organization = Depends(get_current_org),
                     session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory, planner
    run = await planner.start(session, org, goal=body.goal, agreement_ref=body.agreement_ref,
                              allowed=body.allowed_capabilities, max_steps=body.max_steps)
    await session.commit()
    run = await memory.get_run(session, run.id, org.id)
    return memory.run_to_dict(run)


@router.get("/runs", summary="List agent runs")
async def list_runs(limit: int = 50, org: Organization = Depends(get_current_org),
                    session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory
    runs = await memory.list_runs(session, org.id, limit=min(limit, 200))
    return {"runs": [memory.run_to_dict(r, with_steps=False) for r in runs]}


async def _load(session: AsyncSession, org: Organization, run_id: uuid.UUID):
    from openlegal.agent import memory
    run = await memory.get_run(session, run_id, org.id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.get("/runs/{run_id}", summary="One run with its full decision log")
async def get_run(run_id: uuid.UUID, org: Organization = Depends(get_current_org),
                  session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory
    return memory.run_to_dict(await _load(session, org, run_id))


@router.post("/runs/{run_id}/resume", summary="Continue a finished run with a topped-up budget")
async def resume_run(run_id: uuid.UUID, org: Organization = Depends(get_current_org),
                     session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory, planner
    run = await _load(session, org, run_id)
    if run.status == AgentRunStatus.AWAITING_APPROVAL.value:
        raise HTTPException(409, "run is parked for approval; approve or reject it")
    run.max_steps = run.steps_used + 6
    run.completed_at = None
    run = await planner.run_loop(session, org, run)
    await session.commit()
    return memory.run_to_dict(await _load(session, org, run_id))


@router.post("/runs/{run_id}/approve", summary="Approve a parked irreversible action")
async def approve_run(run_id: uuid.UUID, org: Organization = Depends(get_current_org),
                      session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory, planner
    run = await _load(session, org, run_id)
    try:
        await planner.approve(session, org, run)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await session.commit()
    return memory.run_to_dict(await _load(session, org, run_id))


@router.post("/runs/{run_id}/reject", summary="Refuse a parked action and stop the run")
async def reject_run(run_id: uuid.UUID, body: RejectBody, org: Organization = Depends(get_current_org),
                     session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory, planner
    run = await _load(session, org, run_id)
    try:
        await planner.reject(session, org, run, body.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await session.commit()
    return memory.run_to_dict(await _load(session, org, run_id))


@router.get("/runs/{run_id}/messages", summary="Conversation turns for a run")
async def run_messages(run_id: uuid.UUID, org: Organization = Depends(get_current_org),
                       session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    from openlegal.agent import memory
    return {"messages": memory.run_to_dict(await _load(session, org, run_id))["messages"]}


@router.post("/chat", summary="Talk to the agent")
async def chat(body: ChatBody, org: Organization = Depends(get_current_org),
               session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """One entry point, three situations:
      no run            → the message is the goal; a run starts
      run finished      → follow-up; the run resumes with a topped-up budget
      run in flight /   → queued as an interjection; a parked gate stays shut
      awaiting approval
    """
    from openlegal.agent import memory, planner
    if body.run_id is None:
        run = await planner.start(session, org, goal=body.message, agreement_ref=body.agreement_ref,
                                  allowed=None, max_steps=None)
        await session.commit()
        return memory.run_to_dict(await _load(session, org, run.id))

    run = await _load(session, org, body.run_id)
    if run.status == AgentRunStatus.AWAITING_APPROVAL.value:
        await memory.add_message(session, run_id=run.id, role="user", content=body.message, is_interjection=True)
        await session.commit()
        d = memory.run_to_dict(await _load(session, org, run.id))
        d["note"] = "run is parked for approval; message queued, gate unchanged"
        return d
    if run.status in (AgentRunStatus.COMPLETED.value, AgentRunStatus.HALTED.value, AgentRunStatus.FAILED.value):
        await memory.add_message(session, run_id=run.id, role="user", content=body.message)
        run.max_steps = run.steps_used + 6
        run.completed_at = None
        await planner.run_loop(session, org, run)
        await session.commit()
        return memory.run_to_dict(await _load(session, org, run.id))
    await memory.add_message(session, run_id=run.id, role="user", content=body.message, is_interjection=True)
    await session.commit()
    d = memory.run_to_dict(await _load(session, org, run.id))
    d["note"] = "run in flight; message queued as interjection"
    return d
