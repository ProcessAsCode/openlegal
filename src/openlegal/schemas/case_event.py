"""CaseEvent schemas (read-side timeline)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from openlegal.models.case_event import CaseEventActorType, CaseEventType


class VCReferenceSummary(BaseModel):
    """Minimal VC info to render a shield icon + popover in the timeline."""
    model_config = ConfigDict(from_attributes=True)

    vc_id: str
    vc_type: str
    issuer_did: str
    subject_did: str
    vc_hash: str | None = None


class CaseEventResponse(BaseModel):
    """One row from the case timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    type: CaseEventType
    actor_type: CaseEventActorType
    actor_user_id: uuid.UUID | None = None
    actor_label: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any]
    vc_reference_id: uuid.UUID | None = None
    vc: VCReferenceSummary | None = None
    created_at: datetime
