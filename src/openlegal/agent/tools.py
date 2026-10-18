"""Tool broker — what the planner may see and choose from.

Under the declared-process model a capability is invoked by a step someone
wrote, reviewed and signed. Under a planner the SAME capability becomes a
tool the model picked. Identical call, different accountability, so the
broker makes that difference explicit: every tool carries a reversibility
class and the interceptor keys off it.

FAIL SAFE ON UNKNOWNS: anything not classified here is IRREVERSIBLE and
therefore parks for approval. A capability added next month is gated by
default rather than silently available to the planner.

For the legal pilot (spec §7.1): the agent reads the store and writes
obligation / calendar / queue entries only as proposals. Anything that
leaves the boundary or has financial effect is irreversible.
"""

from __future__ import annotations

from typing import Any

from openlegal.core.config import settings
from openlegal.uapf.manifest import get_registry

READ_ONLY = "read_only"
REVERSIBLE = "reversible"
IRREVERSIBLE = "irreversible"

_REVERSIBILITY: dict[str, str] = {
    # reads — store, source connectors (mock in pilot), analysis, evaluation
    "uas.list": READ_ONLY,
    "uas.read": READ_ONLY,
    "agreement.load": READ_ONLY,
    "obligation.scan": READ_ONLY,
    "docus.read": READ_ONLY,
    "sap.read_actuals": READ_ONLY,
    "mip.resolve_classification": READ_ONLY,
    "mip.read_protected": READ_ONLY,
    "ai.classify_clause": READ_ONLY,
    "ai.classify": READ_ONLY,
    "ai.suggest-priority": READ_ONLY,
    "ai.summarize-timeline": READ_ONLY,
    "ai.extract-root-cause": READ_ONLY,
    "ai.draft-response": READ_ONLY,
    "dmn.evaluate": READ_ONLY,
    "governance.evaluate": READ_ONLY,
    "schedule.compute_chain": READ_ONLY,
    "incident.fetch": READ_ONLY,
    "intake.normalize": READ_ONLY,
    # internal writes — undoable inside our boundary, land as proposals
    "register.sync": REVERSIBLE,
    "data.write": REVERSIBLE,
    "event.emit": REVERSIBLE,
    "event.schedule": REVERSIBLE,
    "comm.add-comment": REVERSIBLE,
    "incident.update": REVERSIBLE,
    # leaves the boundary, or has financial effect — human approves
    "comm.send-email": IRREVERSIBLE,
    "notify.alert": IRREVERSIBLE,
    "penalty.accrue": IRREVERSIBLE,
}

# Default allow-list for pilot runs: no boundary-leaving effectors unless
# the run (or AGENT_ALLOWED_CAPABILITIES) opts in explicitly.
_PILOT_DEFAULT = [k for k, v in _REVERSIBILITY.items() if v != IRREVERSIBLE] + ["penalty.accrue", "notify.alert"]


def reversibility(capability: str) -> str:
    return _REVERSIBILITY.get(capability, IRREVERSIBLE)


def default_allowed() -> list[str]:
    if settings.AGENT_ALLOWED_CAPABILITIES:
        return [c.strip() for c in settings.AGENT_ALLOWED_CAPABILITIES.split(",") if c.strip()]
    return list(_PILOT_DEFAULT)


def catalogue(allowed: list[str] | None = None) -> list[dict[str, Any]]:
    """Tools the planner is offered, with reversibility. Only capabilities
    that exist in the UAPF manifest are ever offered."""
    reg = get_registry()
    allow = set(allowed or default_allowed())
    out = []
    for name, d in reg.items():
        if name not in allow:
            continue
        out.append({"name": name, "version": d.version, "summary": d.summary,
                    "reversibility": reversibility(name)})
    return sorted(out, key=lambda t: (t["reversibility"] != READ_ONLY, t["name"]))


def render_for_prompt(tools: list[dict[str, Any]]) -> str:
    lines = []
    for t in tools:
        tag = {READ_ONLY: "", REVERSIBLE: " [reversible]", IRREVERSIBLE: " [IRREVERSIBLE — needs human approval]"}[t["reversibility"]]
        lines.append(f"- {t['name']}{tag}: {t['summary']}")
    return "\n".join(lines)
