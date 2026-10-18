"""UAPF-IP host bridge - HTTP surface.

GET  /uapf/host/manifest             - capability list + host DID/URL
POST /uapf/host/capability/{name}    - dispatch one capability

POST body shape:
    {
      "inputs":  { ... typed input per capability ... },
      "context": {
        "execution_id":         "<uuid>",
        "uapf_package_id":      "<str>",
        "uapf_package_version": "<str>",
        "case_id":              "<uuid>",
        "trace_id":             "<str>"
      }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.core.config import settings
from openlegal.db import get_session
from openlegal.deps import get_current_org  # kept for reference; not used here
from sqlalchemy import select
from openlegal.models.organization import Organization
from openlegal.uapf.dispatcher import UnknownCapabilityError, dispatch
from openlegal.uapf.manifest import manifest_dict


router = APIRouter()


@router.get("/manifest")
async def manifest() -> dict[str, Any]:
    return manifest_dict(settings.HOST_DID, settings.BASE_URL)


@router.post("/capability/{namespace}/{operation}")
async def capability(
    namespace: str,
    operation: str,
    payload: dict[str, Any],
    x_org_slug: str | None = Header(default=None, alias="X-Org-Slug"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Engine callbacks don't carry X-Org-Slug; fall back to the configured default org.
    target_slug = x_org_slug or settings.UAPF_HOST_DEFAULT_ORG_SLUG
    stmt = select(Organization).where(Organization.slug == target_slug)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown org slug for UAPF host callback: {target_slug}",
        )
    capability_name = f"{namespace}.{operation}"

    # The engine POSTs the UAPF-IP v0.1 shape:
    #   { sessionId, stepId, input, guardrails, schemaRef }
    # The host's internal dispatcher expects:
    #   { inputs (dict), context (dict with execution_id/case_id/trace_id) }
    # Map either shape -- engine's flat payload OR our nested form.
    if "input" in payload and "inputs" not in payload:
        inputs = payload.get("input") or {}
        # The engine's sessionId is opaque (e.g. "sess_c3922d01"), not a UUID, so
        # don't put it in execution_id (which is parsed as UUID by the dispatcher
        # for the UAPFCapabilityInvocation row's execution_id FK). Keep it only
        # in trace_id for cross-referencing. Phase 1.5: skip per-invocation persistence
        # on engine-driven callbacks; the parent UAPFSession + engine's audit chain
        # together cover the observability need.
        context = {
            "execution_id": None,
            "step_id": payload.get("stepId"),
            "trace_id": payload.get("sessionId"),
        }
    else:
        inputs = payload.get("inputs") or {}
        context = payload.get("context") or {}

    if not isinstance(inputs, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`input(s)` must be a JSON object",
        )
    if not isinstance(context, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`context` must be a JSON object",
        )

    try:
        return await dispatch(
            session, org,
            capability_name=capability_name,
            inputs=inputs,
            context=context,
        )
    except UnknownCapabilityError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown capability: {capability_name}",
        )
