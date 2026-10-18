"""Governance calendar & scheduling engine (v0.1).

Computes, for a required approval chain (from the competence matrix DMN) and a
hard deadline, the earliest feasible path through the governance calendar:
which sitting of which body, submission cutoffs, completion date, feasibility
and slack. Cadence rules are Cadence-as-Code (governance_calendar_rules.yaml
in the UAPF package); actual moved/cancelled sittings come from `overrides`.

v0.1 scope: forward earliest-completion computation + feasibility/slack.
No external deps beyond PyYAML (already in the stack).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}


def add_working_days(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if d.weekday() < 5:
            remaining -= 1
    return d


@dataclass
class Milestone:
    body: str
    label: str
    kind: str                      # lead_time | recurring | on_demand
    ready_by: date                 # when prerequisites complete / work starts
    submission_deadline: date | None
    sitting_or_completion: date    # sitting date or completion of lead-time step


@dataclass
class ChainPlan:
    deadline: date
    approvals: list[str]
    milestones: list[Milestone] = field(default_factory=list)
    completion: date | None = None
    feasible: bool = False
    slack_days: int | None = None
    reason: str = ""


class GovernanceScheduler:
    def __init__(self, rules: dict[str, Any]):
        self.bodies: dict[str, Any] = rules.get("bodies", {})
        self.overrides = rules.get("overrides") or []

    @classmethod
    def from_package(cls, package_dir: str | Path) -> "GovernanceScheduler":
        p = Path(package_dir) / "resources" / "governance_calendar_rules.yaml"
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")))

    # -- calendar generation -------------------------------------------------
    def sittings(self, body: str, after: date, horizon_days: int = 365) -> list[date]:
        cfg = self.bodies[body]
        out: list[date] = []
        if cfg.get("kind") != "recurring":
            return out
        end = after + timedelta(days=horizon_days)
        if cfg.get("cadence") == "weekly":
            wd = WEEKDAYS[cfg["weekday"].lower()]
            d = after + timedelta(days=(wd - after.weekday()) % 7 or 7)
            while d <= end:
                out.append(d); d += timedelta(days=7)
        elif cfg.get("cadence") == "monthly" and cfg.get("rule", "").startswith("first_"):
            wd = WEEKDAYS[cfg["rule"].split("_", 1)[1].lower()]
            y, m = after.year, after.month
            for _ in range(14):
                first = date(y, m, 1)
                sitting = first + timedelta(days=(wd - first.weekday()) % 7)
                if sitting > after and sitting <= end:
                    out.append(sitting)
                m += 1
                if m == 13: m, y = 1, y + 1
        # apply overrides: {"body":..., "cancel":"YYYY-MM-DD"} / {"move_from":..,"move_to":..}
        for ov in self.overrides:
            if ov.get("body") != body: continue
            if "cancel" in ov:
                out = [d for d in out if d.isoformat() != ov["cancel"]]
            if "move_from" in ov and "move_to" in ov:
                out = [date.fromisoformat(ov["move_to"]) if d.isoformat() == ov["move_from"] else d for d in out]
        return sorted(out)

    def next_sitting_with_cutoff(self, body: str, ready: date) -> tuple[date, date] | None:
        """Earliest sitting whose submission cutoff is still reachable from `ready`."""
        cfg = self.bodies[body]
        cutoff_wd = int(cfg.get("submission_cutoff_working_days", 0))
        for s in self.sittings(body, after=ready):
            cutoff = add_working_days(s, -cutoff_wd)
            if cutoff >= ready:
                return s, cutoff
        return None

    # -- chain computation ---------------------------------------------------
    def compute_chain(self, deadline: date, approvals: list[str],
                      start: date | None = None) -> ChainPlan:
        plan = ChainPlan(deadline=deadline, approvals=list(approvals))
        cur = start or date.today()
        for body in approvals:
            cfg = self.bodies.get(body)
            if cfg is None:
                plan.reason = f"unknown body: {body}"; return plan
            kind = cfg.get("kind")
            label = cfg.get("label", body)
            if kind == "lead_time":
                done = add_working_days(cur, int(cfg.get("lead_working_days", 0)))
                plan.milestones.append(Milestone(body, label, kind, cur, None, done))
                cur = done
            elif kind == "recurring":
                hit = self.next_sitting_with_cutoff(body, cur)
                if hit is None:
                    plan.reason = f"no reachable sitting for {body}"; return plan
                sitting, cutoff = hit
                plan.milestones.append(Milestone(body, label, kind, cur, cutoff, sitting))
                cur = sitting
            elif kind == "on_demand":
                done = cur + timedelta(days=int(cfg.get("lead_calendar_days", 0)))
                plan.milestones.append(Milestone(body, label, kind, cur, None, done))
                cur = done
        plan.completion = cur
        plan.feasible = cur <= deadline
        plan.slack_days = (deadline - cur).days
        plan.reason = "ok" if plan.feasible else "earliest completion after deadline"
        return plan


def plan_to_dict(plan: ChainPlan) -> dict[str, Any]:
    return {
        "deadline": plan.deadline.isoformat(),
        "approvals": plan.approvals,
        "feasible": plan.feasible,
        "completion": plan.completion.isoformat() if plan.completion else None,
        "slack_days": plan.slack_days,
        "reason": plan.reason,
        "milestones": [{
            "body": m.body, "label": m.label, "kind": m.kind,
            "ready_by": m.ready_by.isoformat(),
            "submission_deadline": m.submission_deadline.isoformat() if m.submission_deadline else None,
            "date": m.sitting_or_completion.isoformat(),
        } for m in plan.milestones],
    }


if __name__ == "__main__":  # embedded self-test (algorithm-card style)
    rules = yaml.safe_load(Path(__file__).resolve().parents[3].joinpath(
        "uapf-packages/lv.example.legal.governance_monitoring/resources/governance_calendar_rules.yaml"
    ).read_text())
    s = GovernanceScheduler(rules)
    today = date(2026, 6, 10)
    chain = ["internal_alignment", "valde", "padome", "shareholders"]
    ok = s.compute_chain(date(2026, 8, 1), chain, start=today)
    bad = s.compute_chain(date(2026, 7, 1), chain, start=today)
    import json as _j
    print(_j.dumps({"feasible_case": plan_to_dict(ok), "infeasible_case": plan_to_dict(bad)}, indent=1))
    assert ok.feasible and not bad.feasible, "self-test expectation failed"
    print("SELF-TEST OK")
