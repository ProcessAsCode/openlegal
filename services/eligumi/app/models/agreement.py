"""
SQLModel table definitions for the e-Agreement (UAS) workspace.

This module is imported by app/models/__init__.py so the tables register
on SQLModel.metadata and are created by db.init_db() alongside the
e-invoice tables. Multi-tenant from day one (tenant_id on every owned
row), mirroring the e-invoice models.

Storage model (per the design):
  * `Agreement`          — one row per agreement; holds the *current* version
                           pointer plus denormalised columns for fast
                           list/dashboard rendering.
  * `AgreementRevision`  — immutable; one row per saved version. "Save"
                           never overwrites — it appends v(n+1) and moves
                           the Agreement.current_version pointer. The
                           canonical UAS XML for each revision is stored
                           both in this row (xml) and on disk under
                           /data/agreements/{tenant}/{id}/v{n}.xml.

The on-disk copy is what a future ProcessGitStore will turn into commits;
the DB copy is what the UI reads. Keeping both is the same "canonical doc
+ indexed metadata" pattern the e-invoice Message table uses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


# ---------- Agreement (current-state header) --------------------------------

class Agreement(SQLModel, table=True):
    __tablename__ = "agreement"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True, default=1)

    # Stable public id used inside the UAS XML <identity> and as the
    # ProcessGit path key later. e.g. "AG-2026-0007".
    uas_id: str = Field(index=True)

    # Denormalised from the canonical XML for fast lists / dashboard.
    title: Optional[str] = Field(default=None, index=True)
    agreement_type: Optional[str] = Field(default=None, index=True)  # AgreementType enum
    profile: Optional[str] = Field(default=None, index=True)         # e.g. "services", "nda"
    language: str = Field(default="lv")
    # Lifecycle status mirrors the UAS Status enum:
    # draft | offered | signed | active | suspended | terminated | completed
    status: str = Field(default="draft", index=True)

    # Party summary for the list view (no need to parse XML to render rows).
    buyer_name: Optional[str] = None
    supplier_name: Optional[str] = None

    # Standardisation ratio: clauses sourced from the library / total clauses.
    # 0.0–1.0, the "how standard is this contract?" metric. Null until computed.
    standardization_ratio: Optional[float] = None
    clause_count: int = 0

    # Validation snapshot from the last save.
    last_validation_ok: Optional[bool] = None
    last_validation_errors: int = 0
    last_validation_warnings: int = 0

    # Version pointer + provenance of how this agreement entered the system.
    current_version: int = 0
    source: str = Field(default="manual")  # manual | import | seed
    needs_review: bool = Field(default=False)  # set true for AI-imported drafts

    created_by_user_id: Optional[int] = Field(default=None, foreign_key="app_user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(default=False, index=True)


# ---------- AgreementRevision (immutable version history) -------------------

class AgreementRevision(SQLModel, table=True):
    __tablename__ = "agreement_revision"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True, default=1)
    agreement_id: int = Field(foreign_key="agreement.id", index=True)

    version: int  # 1-based, monotonically increasing per agreement
    xml: str      # canonical UAS XML for this version
    xml_path: Optional[str] = None  # /data/agreements/{tenant}/{id}/v{n}.xml

    # Validation result captured at save time.
    validation_ok: Optional[bool] = None
    validation_report_json: Optional[str] = None  # serialised findings list

    # What changed / why (free text or future commit message).
    change_note: Optional[str] = None

    created_by_user_id: Optional[int] = Field(default=None, foreign_key="app_user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
