"""
UAS data-tree accessors for the Configuration screen.

The per-version tree under {UAS_ROOT}/{version}/ holds the pinned SSOT:
    schema/   e-agreement-{version}.xsd      (read-only core, from GitHub release)
    rules/    e-agreement-{version}.sch      (read-only core)
    profiles/ {name}.json                    (which sections/roles are mandatory)
    clause-library/ {id}.json                (standard clauses + bindings)

The core XSD + Schematron are treated as read-only (pinned to a GitHub
SSOT release). Tenants layer profiles + clause library + optional
Schematron overlays on top — those are editable through the config UI
(not implemented in this phase beyond listing/viewing).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

UAS_ROOT = Path(os.getenv("UAS_ROOT", "/data/uas"))
DEFAULT_VERSION = os.getenv("UAS_VERSION", "0.1")


def available_versions() -> list[str]:
    if not UAS_ROOT.exists():
        return []
    return sorted(
        p.name for p in UAS_ROOT.iterdir()
        if p.is_dir() and (p / "schema").exists()
    )


def _vdir(version: str) -> Path:
    return UAS_ROOT / version


def schema_path(version: str = DEFAULT_VERSION) -> Path:
    return _vdir(version) / "schema" / f"e-agreement-{version}.xsd"


def rules_path(version: str = DEFAULT_VERSION) -> Path:
    return _vdir(version) / "rules" / f"e-agreement-{version}.sch"


def read_schema(version: str = DEFAULT_VERSION) -> str:
    p = schema_path(version)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def read_rules(version: str = DEFAULT_VERSION) -> str:
    p = rules_path(version)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def list_profiles(version: str = DEFAULT_VERSION) -> list[dict]:
    d = _vdir(version) / "profiles"
    out = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                out.append({"name": p.stem, "error": "invalid_json"})
    return out


def get_profile(name: str, version: str = DEFAULT_VERSION) -> dict | None:
    p = _vdir(version) / "profiles" / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_clause_library(version: str = DEFAULT_VERSION) -> list[dict]:
    d = _vdir(version) / "clause-library"
    out = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                out.append({"id": p.stem, "error": "invalid_json"})
    return out


def get_clause(clause_id: str, version: str = DEFAULT_VERSION) -> dict | None:
    """Resolve a libraryRef like 'lib.penalty.late@1.0' to its clause record.
    Matching is by the record's 'ref' field or filename stem."""
    for c in list_clause_library(version):
        if c.get("ref") == clause_id or c.get("id") == clause_id.split("@")[0]:
            return c
    return None


def tree_status(version: str = DEFAULT_VERSION) -> dict:
    return {
        "version": version,
        "schema_present": schema_path(version).exists(),
        "rules_present": rules_path(version).exists(),
        "profiles": len(list_profiles(version)),
        "clauses": len(list_clause_library(version)),
        "root": str(UAS_ROOT),
    }
