"""UAPF outbound bridge.

`start_uapf_run` is the single entry point for OpenLegal code that wants
to delegate a process to an external UAPF engine instead of executing
inline. Used by intake.py:

    if settings.UAPF_ENABLED:
        run = await start_uapf_run(...)
        if run is not None:
            # engine handled it; produce response from run.output_payload
        else:
            # engine unavailable or disabled; fall back to inline
    if run is None:
        triage = await run_triage_inline(...)

Failure semantics: any RuntimeError from the engine (auth, schema, missing
package, timeout) is caught, logged, persisted on the UAPFSession row as
state=failed + error_message, and the function returns None. The caller
then falls back to inline execution. This keeps the demo robust against
engine downtime — the host can always make forward progress.

For long-running processes the engine returns state=running and the
caller is responsible for polling get_session or wiring webhook receipt.
For the lv.itsm.incident.triage package (linear 9-step) the engine
returns terminal state within ~3 seconds, so callers can treat
start_uapf_run as effectively synchronous.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from openlegal.core.config import settings
from openlegal.models.case import Case
from openlegal.models.organization import Organization
from openlegal.models.signal import Signal
from openlegal.models.uapf_session import UAPFSession, UAPFSessionState
from openlegal.uapf.client import UapfClient, UapfEngineError
from openlegal.uapf.manifest import manifest_dict


logger = logging.getLogger(__name__)


def build_host_manifest() -> dict[str, Any]:
    """Produce the `hostManifest` payload the engine receives at start-session.

    The engine uses this to know how to reach back to us for capability
    callbacks: which capabilities we advertise, where to POST them, and
    how to authenticate.
    """
    base = manifest_dict(settings.HOST_DID, settings.BASE_URL)
    return {
        "hostDid": base["host_did"],
        "hostBaseUrl": base["host_base_url"],
        "uapfIpVersion": base["uapf_ip_version"],
        "profiles": ["uapf-ip-orchestrated"],
        "capabilities": base["capabilities"],
    }


async def start_uapf_run(
    session: AsyncSession,
    org: Organization,
    *,
    package_id: str,
    process_id: str,
    input_payload: dict[str, Any],
    case: Case | None = None,
    signal: Signal | None = None,
    package_version: str | None = None,
    trace_id: str | None = None,
) -> UAPFSession | None:
    """Fire a UAPF process on the external engine; persist a session row.

    Returns the persisted UAPFSession (state may be `completed`, `failed`,
    `running`, etc.) on success. Returns None if `UAPF_ENABLED` is false
    or the engine is unreachable — the caller should fall back to inline
    execution.

    The session row is created BEFORE the engine call so that if the
    engine times out or the host process crashes mid-call we still have
    a record of what was attempted.
    """
    if not settings.UAPF_ENABLED:
        logger.debug("UAPF disabled; skipping engine dispatch")
        return None

    if not settings.UAPF_ENGINE_URL:
        logger.warning("UAPF_ENABLED but UAPF_ENGINE_URL is empty; skipping")
        return None

    uapf_session = UAPFSession(
        org_id=org.id,
        package_id=package_id,
        package_version=package_version,
        process_id=process_id,
        case_id=case.id if case is not None else None,
        signal_id=signal.id if signal is not None else None,
        state=UAPFSessionState.STARTING,
        input_payload=input_payload,
        trace_id=trace_id,
    )
    session.add(uapf_session)
    await session.flush()

    client = UapfClient(
        settings.UAPF_ENGINE_URL,
        auth_token=settings.UAPF_ENGINE_AUTH_TOKEN or None,
    )

    try:
        result = await client.start_session(
            package_id=package_id,
            process_id=process_id,
            input_payload=input_payload,
            host_manifest=build_host_manifest(),
            package_version=package_version,
        )
    except UapfEngineError as exc:
        uapf_session.state = UAPFSessionState.FAILED
        uapf_session.error_message = str(exc)
        uapf_session.completed_at = datetime.now(timezone.utc)
        await session.flush()
        logger.warning(
            "UAPF start-session failed for %s/%s on case %s: %s",
            package_id, process_id, getattr(case, "id", None), exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        uapf_session.state = UAPFSessionState.FAILED
        uapf_session.error_message = f"{type(exc).__name__}: {exc}"
        uapf_session.completed_at = datetime.now(timezone.utc)
        await session.flush()
        logger.exception(
            "UAPF start-session unexpected error for %s/%s on case %s",
            package_id, process_id, getattr(case, "id", None),
        )
        return None

    uapf_session.engine_session_id = result.get("sessionId") or result.get("session_id")
    raw_state = (result.get("state") or "running").lower()
    try:
        uapf_session.state = UAPFSessionState(raw_state)
    except ValueError:
        logger.warning("UAPF engine returned unknown state %r; storing as running", raw_state)
        uapf_session.state = UAPFSessionState.RUNNING

    output = result.get("output")
    if output is not None:
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"raw": output}
        uapf_session.output_payload = output

    error_message = result.get("error") or result.get("errorMessage")
    if error_message:
        uapf_session.error_message = str(error_message)

    if uapf_session.state in {
        UAPFSessionState.COMPLETED,
        UAPFSessionState.FAILED,
        UAPFSessionState.ABORTED,
    }:
        uapf_session.completed_at = datetime.now(timezone.utc)

    await session.flush()

    logger.info(
        "UAPF session %s state=%s for %s/%s on case %s",
        uapf_session.engine_session_id,
        uapf_session.state.value,
        package_id, process_id,
        getattr(case, "id", None),
    )
    return uapf_session


async def engine_reachable() -> bool:
    """Cheap probe: is the configured engine answering /health?"""
    if not settings.UAPF_ENABLED or not settings.UAPF_ENGINE_URL:
        return False
    client = UapfClient(
        settings.UAPF_ENGINE_URL,
        auth_token=settings.UAPF_ENGINE_AUTH_TOKEN or None,
    )
    return await client.health()


__all__ = ["start_uapf_run", "engine_reachable", "build_host_manifest"]
