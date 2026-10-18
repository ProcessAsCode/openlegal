"""OpenLegal API entry point.

Boots the FastAPI app, registers routers, sets up middleware
(CORS, trace ID propagation, audit context), and the lifespan hook
that wires DB + Redis + SDK clients.

Operates as a host in the UAPF Integration Protocol (UAPF-IP) ecosystem;
the UAPF engine calls back into this app at `/uapf/host/capability/*`.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openlegal.api import (
    agent,
    store,
    legal_schedule,
    admin,
    audit,
    auth,
    health,
    incidents,
    intake,
    queue,
    reports,
    uapf_admin,
    uapf_host,
)
from openlegal.core.config import settings
from openlegal.core.middleware import TraceIdMiddleware

log = logging.getLogger("openlegal")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown."""
    log.info("openlegal.starting", extra={"env": settings.ENV, "version": "0.1.0-alpha"})
    # Phase 1 will wire DB sessions, Redis pool, SDK client, UAPF engine client here.
    yield
    log.info("openlegal.stopping")


app = FastAPI(
    title="OpenLegal API",
    description="Open, Process-as-Code, AI-native IT Service Management",
    version="0.1.0-alpha",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --- Middleware -------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TraceIdMiddleware)

# --- Routers ----------------------------------------------------------------

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
app.include_router(intake.router, prefix="/api/intake", tags=["intake"])
app.include_router(uapf_admin.router, prefix="/api/uapf", tags=["UAPF"])
app.include_router(legal_schedule.router, prefix="/api/legal", tags=["legal-schedule"])
app.include_router(queue.router, prefix="/api/queue", tags=["queue"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(store.router, prefix="/api/store", tags=["agreement-store"])

# UAPF-IP host bridge — engine calls back into these endpoints.
app.include_router(uapf_host.router, prefix="/uapf/host", tags=["uapf-host"])


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Friendly root response so the demo instance shows life immediately."""
    return {
        "service": "OpenLegal",
        "version": "0.1.0-alpha",
        "docs": "/docs",
        "health": "/api/health",
        "project": "https://github.com/Algomation-AI/OpenLegal",
    }
