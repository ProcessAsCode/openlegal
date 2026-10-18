"""
UAS two-stage validation, mirroring the e-invoice validation philosophy
(XSD for structure, Schematron for cross-field business rules) but using
pure-Python lxml so no Java/Saxon runtime is needed for agreements.

  Stage 1 — XSD          structural conformance to e-agreement-0.1.xsd
  Stage 2 — Schematron   ISO/IEC 19757-3 rules BR-001..BR-010

Schemas are loaded from the per-version pinned tree:
    {UAS_ROOT}/{version}/schema/e-agreement-{version}.xsd
    {UAS_ROOT}/{version}/rules/e-agreement-{version}.sch

A tenant MAY layer extra Schematron overlays (data/uas/{tenant}/overlays/)
which are run after the core rules; that is handled by the config screen
and passed in explicitly, so the core stays a read-only SSOT.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from lxml import etree
from lxml.isoschematron import Schematron

UAS_ROOT = Path(os.getenv("UAS_ROOT", "/data/uas"))
DEFAULT_VERSION = os.getenv("UAS_VERSION", "0.1")
NS = "urn:eagreement:0.1"
SVRL_NS = "{http://purl.oclc.org/dsdl/svrl}"


@dataclass
class Finding:
    layer: str       # "xsd" | "schematron" | "wellformed"
    severity: str    # "error" | "warning"
    message: str
    location: Optional[str] = None
    rule: Optional[str] = None  # e.g. "BR-004"


@dataclass
class ValidationResult:
    well_formed: bool = False
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        return self.well_formed and not self.errors

    def to_json(self) -> list[dict]:
        return [asdict(f) for f in self.findings]


# --- schema loading (cached per version) ------------------------------------

_xsd_cache: dict[str, etree.XMLSchema] = {}
_sch_cache: dict[str, Schematron] = {}


def _version_dir(version: str) -> Path:
    return UAS_ROOT / version


def _load_xsd(version: str) -> Optional[etree.XMLSchema]:
    if version in _xsd_cache:
        return _xsd_cache[version]
    p = _version_dir(version) / "schema" / f"e-agreement-{version}.xsd"
    if not p.exists():
        return None
    schema = etree.XMLSchema(etree.parse(str(p)))
    _xsd_cache[version] = schema
    return schema


def _load_schematron(version: str) -> Optional[Schematron]:
    if version in _sch_cache:
        return _sch_cache[version]
    p = _version_dir(version) / "rules" / f"e-agreement-{version}.sch"
    if not p.exists():
        return None
    # store_report=True so we can read the SVRL and separate warnings from errors
    sch = Schematron(etree.parse(str(p)), store_report=True)
    _sch_cache[version] = sch
    return sch


def clear_cache() -> None:
    """Called by the config screen after a schema/ruleset is activated."""
    _xsd_cache.clear()
    _sch_cache.clear()


# --- validation entry point --------------------------------------------------

def validate(xml: bytes | str, version: str = DEFAULT_VERSION) -> ValidationResult:
    if isinstance(xml, str):
        xml = xml.encode("utf-8")

    result = ValidationResult()

    # Stage 0 — well-formedness
    try:
        doc = etree.fromstring(xml)
    except etree.XMLSyntaxError as e:
        result.findings.append(Finding("wellformed", "error", f"XML nav labi formēts: {e}"))
        return result
    result.well_formed = True

    # Stage 1 — XSD
    schema = _load_xsd(version)
    if schema is None:
        result.findings.append(
            Finding("xsd", "error", f"XSD shēma nav atrasta versijai {version}")
        )
        return result
    if not schema.validate(doc):
        for err in schema.error_log:
            result.findings.append(
                Finding("xsd", "error", err.message, location=f"line {err.line}")
            )
        # XSD failure is fatal — Schematron assumes a structurally valid doc.
        return result

    # Stage 2 — Schematron (cross-field business rules)
    sch = _load_schematron(version)
    if sch is None:
        # Structure is valid; rules layer simply unavailable.
        return result
    sch.validate(doc)
    report = sch.validation_report
    if report is not None:
        for fail in report.iter(f"{SVRL_NS}failed-assert"):
            role = (fail.get("role") or "error").lower()
            severity = "warning" if role == "warning" else "error"
            text_el = fail.find(f"{SVRL_NS}text")
            msg = (text_el.text or "").strip() if text_el is not None else ""
            rule = None
            if ":" in msg and msg.split(":", 1)[0].strip().startswith("BR-"):
                rule = msg.split(":", 1)[0].strip()
            result.findings.append(
                Finding("schematron", severity, msg,
                        location=fail.get("location"), rule=rule)
            )
    return result
