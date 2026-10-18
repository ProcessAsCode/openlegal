"""Shared governance helpers: package resolution + competence-matrix evaluation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PKG_ID = "lv.example.legal.governance_monitoring"
_ROOTS = [Path("uapf-packages"), Path("/app/uapf-packages")]


def pkg_dir(package_id: str = PKG_ID) -> Path:
    for r in _ROOTS:
        if (r / package_id).exists():
            return r / package_id
    return _ROOTS[-1] / package_id


def load_json(rel: str, package_id: str = PKG_ID) -> Any:
    return json.loads((pkg_dir(package_id) / rel).read_text(encoding="utf-8"))


def required_approvals(value_eur: float, material: bool,
                       package_id: str = PKG_ID) -> list[str]:
    """Competence matrix (FIRST hit policy) from dmn/competence_matrix.json."""
    matrix = load_json("dmn/competence_matrix.json", package_id)
    for rule in matrix["rules"]:
        cond = rule.get("when", {})
        v = cond.get("value_eur")
        if v:
            if v.startswith(">") and value_eur > float(v[1:]):
                return rule["then"]["required_approvals"]
            if ".." in v:
                lo, hi = (float(x) for x in v.split(".."))
                if lo <= value_eur <= hi:
                    return rule["then"]["required_approvals"]
            continue
        if cond.get("material") is True and material:
            return rule["then"]["required_approvals"]
        if not cond:
            return rule["then"]["required_approvals"]
    return ["internal_alignment"]
