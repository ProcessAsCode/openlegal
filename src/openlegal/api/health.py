"""Health and readiness endpoints.

These are wired up first so that operators (and Docker Compose healthchecks)
can confirm the service is alive before any business endpoints exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from openlegal.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> Any:
    """Overall service health.

    The database check is load-bearing: it runs SELECT 1 and the endpoint
    returns 503 when it fails. A /health that cannot fail is worse than none
    — it is what the container healthcheck and every external monitor
    believe. Degradable dependencies (UAPF engine, e-Līgumi store, LLM
    provider) are reported but do NOT fail the check: they fall back rather
    than take the service down.
    """
    checks: dict[str, str] = {"api": "ok"}
    ok = True
    try:
        from sqlalchemy import text

        from openlegal.db import session_scope
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        from openlegal.llm import provider
        checks["llm"] = f"{provider.provider_name()}:{'configured' if provider.enabled() else 'stub-fallback'}"
    except Exception:  # noqa: BLE001
        checks["llm"] = "unavailable"
    checks["eligumi_store"] = settings.ELIGUMI_BASE_URL or "not-configured"
    checks["uapf_engine"] = settings.UAPF_ENGINE_URL or "not-configured"

    body = {
        "status": "ok" if ok else "degraded",
        "service": "openlegal",
        "version": "0.1.0-alpha",
        "env": settings.ENV,
        "time": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    return JSONResponse(body, status_code=200 if ok else 503)


@router.get("/sdk/setup-status")
async def sdk_setup_status() -> dict[str, Any]:
    """VeriDocs SDK ↔ Register status (stub).

    Phase 1 will proxy the SDK sidecar's actual readiness signal. Until then,
    surface the configuration so the operator can see what was wired up.
    """
    return {
        "sdk_url": settings.SDK_URL,
        "host_did": settings.HOST_DID,
        "registry_connected": "unchecked-phase0",
        "registry_auth_configured": "unchecked-phase0",
        "registry_authenticated": "unchecked-phase0",
    }


@router.get("/settings/branding")
async def branding() -> dict[str, Any]:
    """Public branding info (no auth required) — used by the frontend shell."""
    return {
        "instance_name": "OpenLegal",
        "primary_color": "#5F47C2",
        "logo_url": None,
    }
