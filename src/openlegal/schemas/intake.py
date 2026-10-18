"""Schemas for the inline-triaged intake response.

The /api/intake/ endpoint runs synchronous triage in the same request
transaction, so the response can carry both the freshly-created signal
*and* a summary of what the triage decided — useful for the operator UI
to render "Routed to noc-l2 with priority P1" immediately.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from openlegal.schemas.signal import SignalResponse


class TriageStepSummary(BaseModel):
    """One step of the triage flow."""
    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str               # "success" | "error" | "skipped"
    duration_ms: int | None = None
    error: str | None = None


class TriageResultResponse(BaseModel):
    """Summary of an inline triage run."""
    case_id: uuid.UUID
    case_number: str
    classification: str | None = None
    priority: str | None = None
    ownership: str | None = None
    group_slug: str | None = None
    group_id: uuid.UUID | None = None
    steps: list[TriageStepSummary]


class IntakeResponse(BaseModel):
    """Body returned by POST /api/intake/."""
    signal: SignalResponse
    triage: TriageResultResponse | None = None
