"""FastAPI request-scoped dependencies.

Phase 1 keeps auth minimal: every API request must carry an `X-Org-Slug`
header that maps to a single Organization. Phase 2 will replace this with
proper JWT-based auth where the org comes from the token claims; the
dependency interface (`get_current_org`) will stay the same, so handlers
do not change.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.db import get_session
from openlegal.models.organization import Organization


async def get_current_org(
    x_org_slug: str | None = Header(default=None, alias="X-Org-Slug"),
    session: AsyncSession = Depends(get_session),
) -> Organization:
    """Resolve the org from the `X-Org-Slug` header.

    Returns 400 if the header is missing, 404 if the slug is unknown.
    """
    if not x_org_slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Org-Slug header",
        )
    stmt = select(Organization).where(Organization.slug == x_org_slug)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown organization slug: {x_org_slug}",
        )
    return org


__all__ = ["get_current_org"]
