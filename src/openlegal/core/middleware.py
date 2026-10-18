"""Middleware: propagates `X-Trace-Id` and actor headers through the request.

Mirrors the OpenDMS pattern so audit logs across OpenLegal, the SDK sidecar,
and OpenDMS all share trace IDs when the two systems are co-deployed.
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Attach `X-Trace-Id` to every request/response, generating one if absent."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        request.state.trace_id = trace_id
        request.state.actor_user_id = request.headers.get("x-actor-user-id", "")
        request.state.actor_email = request.headers.get("x-actor-email", "")

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
