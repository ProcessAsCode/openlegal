"""Working memory: create/read runs, append steps, queue and claim messages.

All writes go through the request's AsyncSession; the caller commits.
`take_pending_messages` claims unconsumed user turns in the same UPDATE that
returns them, so two concurrent iterations cannot both fold in the same
correction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from openlegal.models.agent import AgentMessage, AgentRun, AgentRunStatus, AgentStep


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_run(session: AsyncSession, *, org_id: uuid.UUID, goal: str,
                     allowed: list[str], max_steps: int, model_ref: str,
                     agreement_ref: str | None = None, created_by: uuid.UUID | None = None) -> AgentRun:
    run = AgentRun(org_id=org_id, goal=goal, allowed_capabilities=allowed, max_steps=max_steps,
                   model_ref=model_ref, agreement_ref=agreement_ref, created_by=created_by,
                   status=AgentRunStatus.PLANNING.value, scratchpad={})
    session.add(run)
    await session.flush()
    await add_message(session, run_id=run.id, role="user", content=goal, author_id=created_by,
                      consumed=True)
    return run


async def get_run(session: AsyncSession, run_id: uuid.UUID, org_id: uuid.UUID) -> AgentRun | None:
    # populate_existing: the run is usually already in the identity map with a
    # stale (often empty) steps collection, because steps are inserted through
    # the session rather than appended to the relationship.
    stmt = (select(AgentRun).where(AgentRun.id == run_id, AgentRun.org_id == org_id)
            .options(selectinload(AgentRun.steps), selectinload(AgentRun.messages))
            .execution_options(populate_existing=True))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_runs(session: AsyncSession, org_id: uuid.UUID, limit: int = 50) -> list[AgentRun]:
    stmt = (select(AgentRun).where(AgentRun.org_id == org_id)
            .order_by(AgentRun.created_at.desc()).limit(limit))
    return list((await session.execute(stmt)).scalars().all())


async def next_seq(session: AsyncSession, run_id: uuid.UUID) -> int:
    stmt = select(AgentStep.seq).where(AgentStep.run_id == run_id).order_by(AgentStep.seq.desc()).limit(1)
    last = (await session.execute(stmt)).scalar_one_or_none()
    return (last or 0) + 1


async def add_step(session: AsyncSession, run: AgentRun, *, phase: str, **fields: Any) -> AgentStep:
    step = AgentStep(run_id=run.id, seq=await next_seq(session, run.id), phase=phase, **fields)
    session.add(step)
    await session.flush()
    return step


async def add_message(session: AsyncSession, *, run_id: uuid.UUID, role: str, content: str,
                      author_id: uuid.UUID | None = None, consumed: bool = False,
                      is_interjection: bool = False) -> AgentMessage:
    msg = AgentMessage(run_id=run_id, role=role, content=content, author_id=author_id,
                       consumed_at=_now() if consumed else None, is_interjection=is_interjection)
    session.add(msg)
    await session.flush()
    return msg


async def take_pending_messages(session: AsyncSession, run_id: uuid.UUID) -> list[str]:
    stmt = (update(AgentMessage)
            .where(AgentMessage.run_id == run_id, AgentMessage.role == "user",
                   AgentMessage.consumed_at.is_(None))
            .values(consumed_at=_now())
            .returning(AgentMessage.content))
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def finish_run(session: AsyncSession, run: AgentRun, status: str, *,
                     outcome: dict | None = None, halt_reason: str | None = None) -> None:
    run.status = status
    run.outcome = outcome
    run.halt_reason = halt_reason
    run.completed_at = _now()
    await session.flush()


def run_to_dict(run: AgentRun, *, with_steps: bool = True) -> dict[str, Any]:
    d = {
        "id": str(run.id), "goal": run.goal, "status": run.status, "agreement_ref": run.agreement_ref,
        "max_steps": run.max_steps, "steps_used": run.steps_used, "scratchpad": run.scratchpad,
        "allowed_capabilities": run.allowed_capabilities, "outcome": run.outcome,
        "halt_reason": run.halt_reason, "model_ref": run.model_ref,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if with_steps:
        d["steps"] = [{
            "id": str(s.id), "seq": s.seq, "phase": s.phase, "thought": s.thought,
            "action_capability": s.action_capability, "action_inputs": s.action_inputs,
            "observation": s.observation, "guardrail_verdict": s.guardrail_verdict,
            "guardrail_reason": s.guardrail_reason, "approved_at": s.approved_at.isoformat() if s.approved_at else None,
            "latency_ms": s.latency_ms, "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s in run.steps]
        d["messages"] = [{
            "id": str(m.id), "role": m.role, "content": m.content, "is_interjection": m.is_interjection,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in run.messages]
    return d
