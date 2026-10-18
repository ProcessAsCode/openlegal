"""Signal schemas (intake POST + read)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from openlegal.models.signal import SignalSource, SignalStatus


class SignalCreate(BaseModel):
    """Body of POST /intake.

    Adapters (Zabbix, email, Jira) call this endpoint to drop a normalized
    or raw signal into OpenLegal. The triage process then decides what to do
    with it. The minimum required fields are `source` and `raw_payload`.
    """

    source: SignalSource
    external_id: str | None = Field(default=None, max_length=255)
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any] | None = None
    received_at: datetime | None = Field(
        default=None,
        description="When the source event happened. Defaults to server time.",
    )
    connection_id: uuid.UUID | None = None
    dedupe_hash: str | None = Field(default=None, max_length=64)


class SignalResponse(BaseModel):
    """Read-side representation of a Signal."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    connection_id: uuid.UUID | None = None
    source: SignalSource
    external_id: str | None = None
    received_at: datetime
    normalized_at: datetime | None = None
    case_id: uuid.UUID | None = None
    dedupe_hash: str | None = None
    status: SignalStatus
    created_at: datetime
    updated_at: datetime
