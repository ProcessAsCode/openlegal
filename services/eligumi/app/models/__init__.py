"""SQLModel tables for the standalone e-Līgumi service.

Only the tables the agreement workspace needs. Tenant and User keep the
table names `tenant` / `app_user` so the forked Agreement rows (which carry
foreign keys to them) work unchanged.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field


class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    reg_no: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    __tablename__ = "app_user"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    email: str = Field(index=True)
    display_name: str = ""
    role: str = "editor"
    created_at: datetime = Field(default_factory=datetime.utcnow)


from .agreement import Agreement, AgreementRevision  # noqa: F401,E402
