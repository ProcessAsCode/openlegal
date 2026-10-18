"""
UAS — Universal Agreement Schema support for the e-Agreement workspace.

Public API:
    from uas import validate, serialize, parse, bootstrap
    from uas.store import LocalAgreementStore
    from uas import extract   # AI import (needs API key)

The structured `data` dict that the editor edits and that serialize()
consumes / parse() produces mirrors the XSD one-to-one:

    data = {
      "version": "0.1",
      "profile": "services" | "nda" | "procurement.work-order" | ...,
      "identity": {...}, "provenance": {...}?, "parties": [...],
      "subject": {...}?, "commercials": {...}?, "terms": [clause...]?,
      "serviceLevels": {...}?, "lifecycle": {...}?, "attachments": [...]?,
    }

Round-trip guarantee (tested in the build harness):
    serialize(parse(xml))  ≡  xml   (structurally; validates against the same XSD)
"""
from __future__ import annotations

from . import validate, serialize, parse, bootstrap  # noqa: F401

__all__ = ["validate", "serialize", "parse", "bootstrap"]
__uas_version__ = "0.1"
