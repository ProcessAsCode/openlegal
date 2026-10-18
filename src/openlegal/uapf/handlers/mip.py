"""Microsoft 365 / Purview Information Protection (MIP) capabilities.

  mip.resolve_classification - report the sensitivity label + protection state
                               of a stored object (read-only metadata).
  mip.read_protected         - return the extracted plaintext of a protected
                               object WITHOUT removing its label, plus the audit
                               record id for the access.

Why this exists
---------------
The customer's documents in DOCUS (contracts, emails, presentations) carry Microsoft
Purview sensitivity labels — typically "For Internal Confidential Use Only" —
that apply *protection* (Azure Rights Management encryption), not merely a
marking. An external system cannot read such content at all: a plain Microsoft
Graph read returns an encrypted stream, and downgrading the label to "external"
would destroy the very control the classification exists to enforce (and does
not scale to a contract portfolio).

The supported pattern — and the one this connector defines the slot for — keeps
the label intact and decrypts inside the tenant boundary under audited
authority:

    Graph (discovery / metadata)               read-only
        +
    MIP SDK, service principal granted         decrypt INSIDE the tenant
    Azure RMS "super-user" / content-           (VPS-2, never leaves the customer)
    decryption rights
        -> extract text -> feed the LOCAL model (sovereign / on-prem) -> discard
           plaintext (or re-protect). Every decryption writes a record to the
           Purview Unified Audit Log.

Architectural placement
-----------------------
In the pilot, the real `docus.read` adapter calls this layer to obtain plaintext
for a protected object before clause classification. Because the host advertises
the capability and the package only *requests* it, swapping this mock for the
real MIP-aware adapter is a host-side change with ZERO changes to the UAPF
package (lv.example.legal.governance_monitoring).

v0.1 is a MOCK adapter: it returns sample classification metadata and sample
extracted text so the interface contract and the Connections "Test adapter"
probe are exercisable end-to-end. No Microsoft tenant is contacted.

Real-adapter contract (pilot Discovery must wire, on VPS-2, inside the customer)
----------------------------------------------------------------------
  * Auth:     Entra ID app registration (client credentials); service principal
              added to the Azure RMS super-user grant (or label permissions) so
              it can decrypt protected content. Double Key Encryption (DKE)
              labels additionally require access to the customer-held key.
  * Discover: Microsoft Graph (Sites/Drives/Files or the DOCUS API) — read-only.
  * Decrypt:  MIP SDK (File API) in-process on VPS-2; plaintext never egresses.
  * Audit:    every decrypt emits a `classification.resolved` event here AND is
              recorded in the Purview Unified Audit Log (super-user access is
              logged by Microsoft). The label is NEVER removed or downgraded.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# --- Mock dataset -----------------------------------------------------------
# Keyed by the M365/DOCUS object id. Tied to the two sample contracts so the
# demo coheres with the Agreement Register and the docus_registry mock.
_MOCK_OBJECTS: dict[str, dict[str, Any]] = {
    "DOCUS-OBJ-001": {
        "docus_id": "DOCUS-OBJ-001",
        "title": "IT infrastructure agreement (UAS-EXAMPLE-001)",
        "label": "For Internal Confidential Use Only",
        "label_id": "f1a2b3c4-0001-mip-example-internal-confidential",
        "protected": True,            # Azure RMS encryption applied
        "owner": "legal@example.lv",
        "mock_text": (
            "MASTER IT INFRASTRUCTURE AGREEMENT. Term: 2024-08-01 to 2026-08-01. "
            "Contract value EUR 1,400,000. Renewal notice window: 60 days. "
            "Amendments above EUR 1,000,000 require Valde, Padome and shareholder consent."
        ),
    },
    "DOCUS-OBJ-002": {
        "docus_id": "DOCUS-OBJ-002",
        "title": "Software maintenance agreement (UAS-EXAMPLE-002)",
        "label": "For Internal Confidential Use Only",
        "label_id": "f1a2b3c4-0001-mip-example-internal-confidential",
        "protected": True,
        "owner": "legal@example.lv",
        "mock_text": (
            "SOFTWARE MAINTENANCE AGREEMENT. Expiry 2026-07-25. "
            "Approved value EUR 350,000. Spend alert threshold 80%."
        ),
    },
    "DOCUS-OBJ-PUB": {
        "docus_id": "DOCUS-OBJ-PUB",
        "title": "Published service catalogue (unrestricted)",
        "label": "Public",
        "label_id": "f1a2b3c4-0009-mip-example-public",
        "protected": False,           # readable without decryption
        "owner": "legal@example.lv",
        "mock_text": "Public service catalogue. No restriction.",
    },
}

# In mock mode the in-tenant service principal is assumed to hold decryption
# rights for the internal-confidential label (the whole point of the pattern).
_CAN_DECRYPT = True


def _registry_summary() -> dict[str, Any]:
    return {
        "adapter": "mock",
        "count": len(_MOCK_OBJECTS),
        "registry": {
            k: {"title": v["title"], "label": v["label"], "protected": v["protected"]}
            for k, v in _MOCK_OBJECTS.items()
        },
        "can_decrypt": _CAN_DECRYPT,
        "note": "v0.1 mock. Real adapter: Graph discovery + MIP SDK super-user "
                "decrypt on VPS-2; label preserved; access audited in Purview.",
    }


async def resolve_classification(session, org, inputs, context) -> dict[str, Any]:
    """Report a stored object's sensitivity label + protection state (read-only).

    inputs: {"object_id": "<DOCUS/M365 id>"}  — omit to list the mock registry.
    """
    object_id = (inputs or {}).get("object_id") or (inputs or {}).get("docus_id")
    if not object_id:
        return _registry_summary()
    obj = _MOCK_OBJECTS.get(object_id)
    if obj is None:
        return {"found": False, "object_id": object_id, "adapter": "mock"}
    return {
        "found": True,
        "object_id": object_id,
        "label": obj["label"],
        "label_id": obj["label_id"],
        "protected": obj["protected"],
        "can_decrypt": _CAN_DECRYPT if obj["protected"] else True,
        "owner": obj["owner"],
        "adapter": "mock",
    }


async def read_protected(session, org, inputs, context) -> dict[str, Any]:
    """Return the extracted plaintext of a (possibly protected) object.

    The label is NEVER removed. In the real adapter the decryption happens
    in-tenant on VPS-2 via the MIP SDK super-user grant and is recorded in the
    Purview Unified Audit Log; here we return a synthetic audit id.

    inputs: {"object_id": "<id>"}  — omit to list the mock registry (so the
            Connections "Test adapter" probe has a record count to report).
    """
    object_id = (inputs or {}).get("object_id") or (inputs or {}).get("docus_id")
    if not object_id:
        return _registry_summary()
    obj = _MOCK_OBJECTS.get(object_id)
    if obj is None:
        return {"found": False, "object_id": object_id, "adapter": "mock"}
    if obj["protected"] and not _CAN_DECRYPT:
        return {
            "found": True, "object_id": object_id, "decrypted": False,
            "label": obj["label"], "protected": True, "adapter": "mock",
            "error": "service principal lacks RMS decryption rights for this label",
        }
    audit_event_id = str(uuid.uuid4())
    return {
        "found": True,
        "object_id": object_id,
        "label": obj["label"],            # label preserved, not stripped
        "protected": obj["protected"],
        "decrypted": obj["protected"],    # decryption only needed if protected
        "text": obj["mock_text"],
        "audit_event_id": audit_event_id,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "audit_sink": "purview_unified_audit_log (mock)",
        "adapter": "mock",
    }
