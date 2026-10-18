"""Legal-domain capabilities: docus.read, sap.read_actuals, governance.evaluate,
schedule.compute_chain, notify.alert.

Host side of lv.example.legal.governance_monitoring. DOCUS/SAP are mock adapters in
v0.1 (read from the package's mock-data/, read-only) — the interface is the
contract; the customer's real adapters replace the file reads during pilot Discovery.
Alerts persist as JSON lines under the attachments volume.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from openlegal.services.governance import PKG_ID, load_json, pkg_dir, required_approvals
from openlegal.services.scheduler import GovernanceScheduler, plan_to_dict

ALERTS_FILE = Path("/data/openlegal/attachments/governance_alerts.jsonl")


def _pkg(context) -> str:
    return (context or {}).get("uapf_package_id") or PKG_ID


async def docus_read(session, org, inputs, context):
    """Mock DOCUS connector: contract registry metadata (read-only)."""
    reg = load_json("mock-data/docus_registry.json", _pkg(context))
    docus_id = (inputs or {}).get("docus_id")
    if docus_id:
        entry = reg.get(docus_id)
        if entry is None:
            return {"found": False, "docus_id": docus_id}
        return {"found": True, "docus_id": docus_id, **entry, "adapter": "mock"}
    return {"registry": reg, "count": len(reg), "adapter": "mock"}


async def sap_read_actuals(session, org, inputs, context):
    """Mock SAP connector: actual spend + payments per contract (read-only)."""
    actuals = load_json("mock-data/sap_actuals.json", _pkg(context))
    sap_id = (inputs or {}).get("sap_contract_id")
    if sap_id:
        row = actuals.get(sap_id)
        if row is None:
            return {"found": False, "sap_contract_id": sap_id}
        return {"found": True, "sap_contract_id": sap_id, **row, "adapter": "mock"}
    return {"actuals": actuals, "count": len(actuals), "adapter": "mock"}


async def governance_evaluate(session, org, inputs, context):
    """Competence matrix: which approvals does this value/materiality require."""
    value = float((inputs or {}).get("value_eur", 0))
    material = bool((inputs or {}).get("material", False))
    approvals = required_approvals(value, material, _pkg(context))
    return {"value_eur": value, "material": material,
            "required_approvals": approvals,
            "decision_table": "dmn/competence_matrix.json"}


async def schedule_compute_chain(session, org, inputs, context):
    """Deadline-driven critical path through the governance calendar."""
    inputs = inputs or {}
    deadline = date.fromisoformat(str(inputs["deadline"])[:10])
    start = inputs.get("start")
    start_d = date.fromisoformat(str(start)[:10]) if start else None
    approvals = inputs.get("approvals")
    if not approvals:
        approvals = required_approvals(float(inputs.get("value_eur", 0)),
                                       bool(inputs.get("material", False)),
                                       _pkg(context))
    sched = GovernanceScheduler.from_package(pkg_dir(_pkg(context)))
    plan = sched.compute_chain(deadline, approvals, start=start_d)
    return plan_to_dict(plan)


async def notify_alert(session, org, inputs, context):
    """Record a governance alert (board channel; email adapter is Phase-1 work)."""
    inputs = inputs or {}
    alert = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "org": getattr(org, "slug", None),
        "severity": inputs.get("severity", "info"),
        "contract": inputs.get("contract"),
        "obligation": inputs.get("obligation"),
        "state": inputs.get("state"),
        "action": inputs.get("action"),
        "message": inputs.get("message"),
        "detail": inputs.get("detail"),
    }
    ALERTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return {"recorded": True, "alert_id": alert["id"], "channel": "board"}


def read_alerts(org_slug: str | None = None, limit: int = 100) -> list[dict]:
    """Helper for the API: newest-first alert list."""
    if not ALERTS_FILE.exists():
        return []
    rows = [json.loads(l) for l in ALERTS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if org_slug:
        rows = [r for r in rows if r.get("org") == org_slug]
    return list(reversed(rows))[:limit]
