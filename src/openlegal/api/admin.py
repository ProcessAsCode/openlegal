"""Admin / demo-control router.

POST /api/admin/reset      Wipe all tenant data and re-seed the demo org.
POST /api/admin/seed       Seed the demo org only if it doesn't already exist.

Both endpoints are open in the API layer; HTTP Basic Auth at the Apache
reverse-proxy layer is what protects them in deployment. Locally you can
hit them directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from openlegal.services.seed import reset_and_seed, seed_if_empty


router = APIRouter()


@router.post("/seed", summary="Seed the demo org if absent (idempotent)")
async def post_seed() -> dict[str, Any]:
    return await seed_if_empty()


@router.post("/reset", summary="Wipe all tenant data and reseed the demo org")
async def post_reset() -> dict[str, Any]:
    return await reset_and_seed()
