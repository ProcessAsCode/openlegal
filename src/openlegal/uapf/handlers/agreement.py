"""agreement.* + obligation.scan + penalty.accrue + event.schedule capabilities.

Host side of the lv.proc.it_agreement.monitoring package. These operate on the
UAS agreement co-versioned inside the package (not on OpenLegal cases): load the
agreement, scan obligations into per-obligation states, compute late-performance
penalties, and record a scheduled monitoring tick.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401
from openlegal.models.organization import Organization  # noqa: F401

_PACKAGE_ROOTS = [Path("uapf-packages"), Path("/app/uapf-packages"),
                  Path("/srv/openlegal/uapf-packages")]


def _pkg_root(package_id):
    for root in _PACKAGE_ROOTS:
        cand = root / package_id
        if cand.exists():
            return cand
    return _PACKAGE_ROOTS[0] / package_id


def _default_package(context):
    return context.get("uapf_package_id") or "lv.proc.it_agreement.monitoring"


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


async def load_agreement(session, org, inputs, context):
    package_id = inputs.get("package_id") or _default_package(context)
    agdir = _pkg_root(package_id) / "agreements"
    ref = inputs.get("agreement_id") or inputs.get("agreement_ref")
    chosen = None
    files = sorted(agdir.glob("*.uas.json")) if agdir.exists() else []
    if ref:
        for c in files:
            try:
                d = json.loads(c.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("id") == ref or c.stem.startswith(str(ref)):
                chosen = c
                break
    if chosen is None and files:
        chosen = files[0]
    if chosen is None:
        raise LookupError("agreement.load: no UAS agreement under %s" % agdir)
    agreement = json.loads(chosen.read_text(encoding="utf-8"))
    return {"agreement": agreement, "agreement_id": agreement.get("id"),
            "source": str(chosen)}


async def scan_obligations(session, org, inputs, context):
    agreement = inputs.get("agreement")
    if agreement is None:
        agreement = (await load_agreement(session, org, inputs, context))["agreement"]
    as_of = _parse_date(inputs.get("as_of")) or datetime.now(timezone.utc).date()
    states = []
    for ob in agreement.get("obligations", []):
        ob_type = ob.get("type")
        due = _parse_date(ob.get("due_date") or ob.get("due"))
        if ob_type == "renewal":
            state = "window_open"
        elif due is not None:
            days = (due - as_of).days
            state = "overdue" if days < 0 else ("due_soon" if days <= 14 else "scheduled")
        else:
            state = "due_soon" if ob.get("mode") == "auto" else "tracked"
        st = {"obligation_id": ob.get("id"), "obligation_type": ob_type,
              "state": state, "mode": ob.get("mode", "auto"),
              "jira_issue_type": ob.get("jira_issue_type", "Task")}
        if due:
            st["due_date"] = due.isoformat()
        if ob.get("jira"):
            st["existing_jira"] = ob["jira"]
        states.append(st)
    return {"obligation_states": states, "count": len(states),
            "as_of": as_of.isoformat()}


async def penalty_accrue(session, org, inputs, context):
    overdue = float(inputs.get("overdue_amount") or 0)
    days = float(inputs.get("days_late") or 0)
    per_day = float(inputs.get("per_day_pct") or 0)
    cap_pct = float(inputs.get("cap_pct") or 0)
    price = float(inputs.get("contract_price") or 0)
    raw = overdue * (per_day / 100.0) * days
    cap = price * (cap_pct / 100.0) if price and cap_pct else None
    capped = cap is not None and raw > cap
    amount = round(cap if capped else raw, 2)
    return {"penalty_amount": amount, "capped": capped,
            "uncapped_amount": round(raw, 2),
            "note": "Proposed penalty claim; human approval required."}


async def event_schedule(session, org, inputs, context):
    return {"scheduled": True,
            "at": inputs.get("at") or inputs.get("next_tick"),
            "kind": inputs.get("kind") or "monitoring_tick"}
