"""Capability dispatcher.

Routes an incoming capability request to its handler, records a
UAPFCapabilityInvocation row (when an execution_id is supplied), and
serializes errors so the engine can act on them instead of getting a 500.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.organization import Organization
from openlegal.models.uapf_execution import (
    UAPFCapabilityInvocation,
    UAPFInvocationStatus,
)
from openlegal.uapf.manifest import get_handler


class UnknownCapabilityError(KeyError):
    """Raised when the requested capability is not in the manifest."""


async def dispatch(
    session: AsyncSession,
    org: Organization,
    *,
    capability_name: str,
    inputs: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    descriptor = get_handler(capability_name)
    if descriptor is None:
        raise UnknownCapabilityError(capability_name)

    execution_id_str = context.get("execution_id")
    execution_id = uuid.UUID(execution_id_str) if execution_id_str else None

    invocation = UAPFCapabilityInvocation(
        org_id=org.id,
        execution_id=execution_id or uuid.uuid4(),
        capability_name=capability_name,
        capability_version=descriptor.version,
        request_payload=inputs,
        status=UAPFInvocationStatus.PENDING,
        started_at=datetime.now(timezone.utc),
        trace_id=context.get("trace_id"),
    )

    persistent = execution_id is not None
    if persistent:
        session.add(invocation)
        await session.flush()

    t0 = time.perf_counter()
    try:
        output = await descriptor.handler(session, org, inputs, context)
        duration_ms = int((time.perf_counter() - t0) * 1000)
        if persistent:
            invocation.response_payload = output
            invocation.status = UAPFInvocationStatus.SUCCESS
            invocation.completed_at = datetime.now(timezone.utc)
            invocation.duration_ms = duration_ms
        return {
            "invocation_id": str(invocation.id) if persistent else None,
            "capability": capability_name,
            "version": descriptor.version,
            "status": "success",
            "duration_ms": duration_ms,
            "output": output,
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        msg = f"{type(exc).__name__}: {exc}"
        if persistent:
            invocation.status = UAPFInvocationStatus.ERROR
            invocation.error_message = msg
            invocation.completed_at = datetime.now(timezone.utc)
            invocation.duration_ms = duration_ms
        return {
            "invocation_id": str(invocation.id) if persistent else None,
            "capability": capability_name,
            "version": descriptor.version,
            "status": "error",
            "duration_ms": duration_ms,
            "error": msg,
        }


__all__ = ["UnknownCapabilityError", "dispatch"]
