"""Tenant bootstrap and the API-key gate.

Single-tenant by default: ELIGUMI_TENANT_SLUG (default "demo"). The {tenant}
path segment must match it. A synthetic service user is attached so the
forked routes (which expect request.state.tenant_user) work unchanged.
UI access is protected by HTTP basic auth (ELIGUMI_UI_USER / _PASSWORD);
JSON API access by X-Api-Key (ELIGUMI_API_KEY). Either may be left unset
in a closed pilot network, in which case that surface is open.
"""
from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request
from sqlmodel import select

from db import get_session_ctx as get_session
from models import Tenant, User

TENANT_SLUG = os.getenv("ELIGUMI_TENANT_SLUG", "demo")
TENANT_NAME = os.getenv("ELIGUMI_TENANT_NAME", "Demo organizācija")


def ensure_tenant() -> None:
    with get_session() as s:
        t = s.exec(select(Tenant).where(Tenant.slug == TENANT_SLUG)).first()
        if t is None:
            t = Tenant(slug=TENANT_SLUG, name=TENANT_NAME)
            s.add(t)
            s.commit()
            s.refresh(t)
        u = s.exec(select(User).where(User.tenant_id == t.id)).first()
        if u is None:
            s.add(User(tenant_id=t.id, email="service@eligumi.local",
                       display_name="e-Līgumi service", role="admin"))
            s.commit()


def api_key_ok(request: Request) -> None:
    """Shared-secret gate. The OpenLegal app and the agent both present it;
    an empty ELIGUMI_API_KEY leaves the surface open for a closed network."""
    key = os.getenv("ELIGUMI_API_KEY")
    if not key:
        return
    if not secrets.compare_digest(request.headers.get("x-api-key", ""), key):
        raise HTTPException(status_code=401, detail="invalid api key")
