"""Case schemas (list, detail, create, transition)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from openlegal.models.case import CaseOwnership, CasePriority, CaseStatus


class CaseCreate(BaseModel):
    """Body of POST /incidents.

    Used by adapters that produce a fully-formed case (e.g. operator manually
    opening one from the UI) rather than going through /intake. For the
    sandbox PoC, /intake → triage → case is the primary path; this endpoint
    is the secondary "manual open" path.
    """

    title: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    priority: CasePriority | None = None
    classification_id: uuid.UUID | None = None
    service_tier_id: uuid.UUID | None = None
    signal_id: uuid.UUID | None = Field(
        default=None,
        description="Link to the originating signal, if any.",
    )


class CaseTransition(BaseModel):
    """Body of POST /incidents/{id}/transition."""

    to_status: CaseStatus
    reason: str | None = Field(default=None, max_length=512)


class CaseSummary(BaseModel):
    """List-view representation: just enough to render a queue row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_number: str
    title: str
    status: CaseStatus
    priority: CasePriority | None = None
    ownership: CaseOwnership | None = None
    assigned_group_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None
    opened_at: datetime
    sla_resolution_due_at: datetime | None = None
    updated_at: datetime


class CaseDetail(CaseSummary):
    """Detail-view representation: adds the heavier fields."""

    description: str | None = None
    classification_id: uuid.UUID | None = None
    service_tier_id: uuid.UUID | None = None
    jira_mirror_key: str | None = None
    triaged_at: datetime | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    sla_first_response_due_at: datetime | None = None
    state_snapshot: dict = Field(default_factory=dict)
    created_at: datetime
