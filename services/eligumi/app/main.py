"""e-Līgumi — UAS agreement store (OpenLegal component C5).

API only. This container owns the agreements, the UAS schema tree and the
validation rules; the human interface lives in the OpenLegal app so there is
one product and one login rather than two.

  /api/agreements...   read + write, see api.py
  /api/health          SELECT 1 + store dir check; 503 when broken
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

import db as _db
from api import router as api_router
from tenant import TENANT_SLUG, ensure_tenant

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("eligumi")

app = FastAPI(title="e-Līgumi (UAS store)", version="0.2.0", docs_url="/api/docs")


@app.on_event("startup")
def _startup() -> None:
    _db.init_db()
    ensure_tenant()
    log.info("e-Līgumi store ready; tenant=%s", TENANT_SLUG)


@app.get("/", include_in_schema=False)
def _root():
    return {"service": "eligumi", "role": "UAS agreement store",
            "ui": "served by the OpenLegal app", "api": "/api/agreements",
            "health": "/api/health"}


@app.get("/api/health")
def health():
    from uas.store import AGREEMENTS_ROOT
    ok, detail = True, {}
    try:
        with _db.engine.connect() as c:
            c.execute(text("SELECT 1"))
        detail["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail["db"] = f"error: {type(exc).__name__}"
    detail["agreements_root"] = str(AGREEMENTS_ROOT)
    detail["agreements_root_writable"] = (
        os.access(AGREEMENTS_ROOT, os.W_OK) if AGREEMENTS_ROOT.exists() else False)
    if not detail["agreements_root_writable"]:
        ok = False
    return JSONResponse({"ok": ok, **detail}, status_code=200 if ok else 503)


app.include_router(api_router, prefix="/api", tags=["agreements"])
