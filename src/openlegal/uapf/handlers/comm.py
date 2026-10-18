"""comm.* + jira.mirror UAPF capabilities - Phase 1 stubs.

These record the *intent* (timeline event + typed comment row) so the rest
of the system can be tested end-to-end without real external clients.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.models.case import Case
from openlegal.models.case_event import (
    CaseEvent,
    CaseEventActorType,
    CaseEventType,
)
from openlegal.models.comment import Comment, CommentType
from openlegal.models.organization import Organization


async def add_comment(session, org, inputs, context):
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"comm.add_comment: case {case_id} not in org {org.slug}")

    comment_type = CommentType(inputs.get("type", "internal_note"))

    comment = Comment(
        org_id=org.id,
        case_id=case_id,
        type=comment_type,
        body=inputs["body"],
        body_format=inputs.get("body_format", "markdown"),
        ai_decision_id=(
            uuid.UUID(inputs["ai_decision_id"])
            if inputs.get("ai_decision_id") else None
        ),
    )
    session.add(comment)
    await session.flush()

    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case_id,
            type=CaseEventType.COMMENT_ADDED,
            actor_type=CaseEventActorType.UAPF,
            actor_label=context.get("uapf_package_id"),
            trace_id=context.get("trace_id"),
            payload={
                "comment_id": str(comment.id),
                "type": comment_type.value,
                "body_preview": inputs["body"][:140],
            },
        )
    )

    return {"comment_id": str(comment.id), "type": comment_type.value}


async def send_email(session, org, inputs, context):
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"comm.send_email: case {case_id} not in org {org.slug}")

    recipients = inputs.get("to") or inputs.get("recipients") or []
    subject = inputs.get("subject") or "(no subject)"
    body = inputs.get("body") or ""

    pseudo_message_id = f"<stub-{uuid.uuid4().hex}@openlegal.local>"
    sent_at = datetime.now(timezone.utc)

    comment = Comment(
        org_id=org.id,
        case_id=case_id,
        type=CommentType.CUSTOMER_REPLY_SENT,
        body=body,
        body_format=inputs.get("body_format", "markdown"),
        sent_at=sent_at,
        recipients={"to": recipients, "subject": subject},
        ai_decision_id=(
            uuid.UUID(inputs["ai_decision_id"])
            if inputs.get("ai_decision_id") else None
        ),
    )
    session.add(comment)
    await session.flush()

    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case_id,
            type=CaseEventType.CUSTOMER_REPLY_SENT,
            actor_type=CaseEventActorType.UAPF,
            actor_label=context.get("uapf_package_id"),
            trace_id=context.get("trace_id"),
            payload={
                "message_id": pseudo_message_id,
                "to": recipients,
                "subject": subject,
                "delivery": "stub",
            },
        )
    )
    return {
        "message_id": pseudo_message_id,
        "delivery": "stub",
        "comment_id": str(comment.id),
    }


async def mirror(session, org, inputs, context):
    case_id = uuid.UUID(inputs["case_id"])
    case = await session.get(Case, case_id)
    if case is None or case.org_id != org.id:
        raise LookupError(f"jira.mirror: case {case_id} not in org {org.slug}")

    if not case.jira_mirror_key:
        case.jira_mirror_key = f"STUB-{case.case_number}"
    payload = {
        "jira_mirror_key": case.jira_mirror_key,
        "fields_synced": inputs.get("fields") or ["status", "priority", "title"],
        "delivery": "stub",
    }
    session.add(
        CaseEvent(
            org_id=org.id,
            case_id=case_id,
            type=CaseEventType.JIRA_SYNCED,
            actor_type=CaseEventActorType.UAPF,
            actor_label=context.get("uapf_package_id"),
            trace_id=context.get("trace_id"),
            payload=payload,
        )
    )
    return payload
