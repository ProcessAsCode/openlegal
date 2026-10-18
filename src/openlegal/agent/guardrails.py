"""Guardrail interceptor — sits between the planner and the effectors.

Under a declared process guardrails validate the package before it runs:
static, upstream, outside the loop. With a planner that becomes decoration,
because the planner composes action sequences nobody validated. So the
check moves inside the loop and in front of every action:

  budget      — steps_used < max_steps, always
  allow-list  — the run's allowed_capabilities (defaults from the broker)
  reversib.   — IRREVERSIBLE parks the run for a human (require_approval)
  repetition  — the same capability+inputs twice in a row is denied; a
                planner that loops on a failing call must stop, not retry
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from openlegal.agent import tools as broker
from openlegal.models.agent import GuardrailVerdict


@dataclass(frozen=True)
class Verdict:
    verdict: str
    reason: str

    @property
    def blocked(self) -> bool:
        return self.verdict != GuardrailVerdict.ALLOW.value


def fingerprint(capability: str, inputs: dict[str, Any]) -> str:
    raw = capability + json.dumps(inputs or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def check(*, capability: str, inputs: dict[str, Any], steps_used: int, max_steps: int,
          allowed: list[str], previous_fingerprints: list[str],
          approved_fingerprint: str | None = None) -> Verdict:
    if steps_used >= max_steps:
        return Verdict(GuardrailVerdict.DENY.value, f"step budget exhausted ({max_steps})")
    if capability not in allowed:
        return Verdict(GuardrailVerdict.DENY.value, f"'{capability}' is not in this run's allow-list")
    fp = fingerprint(capability, inputs)
    if previous_fingerprints and previous_fingerprints[-1] == fp:
        return Verdict(GuardrailVerdict.DENY.value, "identical action repeated back-to-back")
    if broker.reversibility(capability) == broker.IRREVERSIBLE and approved_fingerprint != fp:
        return Verdict(GuardrailVerdict.REQUIRE_APPROVAL.value,
                       f"'{capability}' has irreversible or financial effect and requires human approval")
    return Verdict(GuardrailVerdict.ALLOW.value, "ok")


def policy_summary(max_steps: int, allowed: list[str]) -> dict[str, Any]:
    return {
        "max_steps": max_steps,
        "allowed_capabilities": allowed,
        "irreversible_actions": "require human approval before execution",
        "repeated_identical_action": "denied",
        "unknown_capability": "treated as irreversible",
        "human_final_decision": "every proposal stays in 'priekšlikums' status until a human user acts on it",
    }
