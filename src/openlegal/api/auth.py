"""auth router — Phase 1 deliverable.

Endpoints declared in the OpenLegal concept (README.md, "API surface" section)
will be implemented here in Phase 1. For now this file is a placeholder so
the FastAPI app boots without import errors.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def _placeholder() -> dict[str, str]:
    """Placeholder endpoint so the router has at least one route during Phase 0."""
    return {"status": "not-implemented-yet", "router": "auth"}
