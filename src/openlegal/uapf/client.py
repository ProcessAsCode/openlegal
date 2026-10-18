"""UapfClient — thin async wrapper around the UAPF-IP v0.1 REST surface
of the uapf-engine reference runtime.

Mirrors the OpenDMS implementation. The same client serves both
synchronous (await start-session) and asynchronous (poll get-session)
usage patterns.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class UapfEngineError(RuntimeError):
    """Engine returned an error response or was unreachable."""


class UapfClient:
    """Thin httpx-based client for one UAPF engine deployment."""

    def __init__(
        self,
        engine_url: str,
        auth_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not engine_url:
            raise ValueError("UapfClient: engine_url is required")
        self.engine_url = engine_url.rstrip("/")
        self.auth_token = auth_token or None
        self.timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_token:
            h["Authorization"] = f"Bearer {self.auth_token}"
        return h

    async def start_session(
        self,
        package_id: str,
        process_id: str,
        input_payload: Any,
        host_manifest: dict[str, Any],
        package_version: str | None = None,
    ) -> dict[str, Any]:
        """POST /uapf/start-session.

        For short linear processes (e.g. lv.itsm.incident.triage) the engine
        runs the whole flow before responding; the returned dict carries
        sessionId, state, and the final output. For long-running processes
        it returns state=running and the caller polls get_session.
        """
        body: dict[str, Any] = {
            "packageId": package_id,
            "processId": process_id,
            "input": input_payload,
            "hostManifest": host_manifest,
        }
        if package_version:
            body["packageVersion"] = package_version

        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(
                f"{self.engine_url}/uapf/start-session",
                headers=self._headers(),
                json=body,
            )
            if r.status_code >= 400:
                raise UapfEngineError(
                    f"start-session returned {r.status_code}: {r.text[:500]}"
                )
            return r.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(
                f"{self.engine_url}/uapf/sessions/{session_id}",
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise UapfEngineError(
                    f"get-session {session_id} returned {r.status_code}: {r.text[:500]}"
                )
            return r.json()

    async def get_session_audit(self, session_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(
                f"{self.engine_url}/uapf/sessions/{session_id}/audit",
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise UapfEngineError(
                    f"get-session-audit {session_id} returned {r.status_code}: {r.text[:500]}"
                )
            return r.json()

    async def evaluate_decision(
        self,
        package_id: str,
        decision_id: str,
        input_payload: Any,
    ) -> dict[str, Any]:
        """POST /uapf/evaluate-decision."""
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(
                f"{self.engine_url}/uapf/evaluate-decision",
                headers=self._headers(),
                json={
                    "packageId": package_id,
                    "decisionId": decision_id,
                    "input": input_payload,
                },
            )
            if r.status_code >= 400:
                raise UapfEngineError(
                    f"evaluate-decision returned {r.status_code}: {r.text[:500]}"
                )
            return r.json()

    async def list_packages(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(
                f"{self.engine_url}/uapf/packages",
                headers=self._headers(),
            )
            if r.status_code >= 400:
                raise UapfEngineError(
                    f"list-packages returned {r.status_code}: {r.text[:500]}"
                )
            return r.json()

    async def health(self) -> bool:
        """Cheap reachability + liveness check."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                r = await http.get(f"{self.engine_url}/health")
                return r.status_code == 200
        except Exception:
            return False


__all__ = ["UapfClient", "UapfEngineError"]
