"""
UAS parser — canonical XML -> structured `data` dict (inverse of serialize).

Used when the editor loads an existing instance and after AI import to
re-render the extracted draft in the form. Round-trip property:
serialize(parse(xml)) is structurally equivalent to xml.
"""
from __future__ import annotations

from typing import Optional
from lxml import etree

NS = "urn:eagreement:0.1"


def _q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def _text(el, tag: str) -> Optional[str]:
    if el is None:
        return None
    child = el.find(_q(tag))
    return child.text if child is not None and child.text is not None else None


def _bool(el, tag: str):
    v = _text(el, tag)
    if v is None:
        return None
    return v.strip().lower() == "true"


def _texts(el, tag: str) -> list[str]:
    if el is None:
        return []
    return [c.text for c in el.findall(_q(tag)) if c.text]


def parse(xml: bytes | str) -> dict:
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    root = etree.fromstring(xml)
    data: dict = {
        "version": root.get("version") or "0.1",
        "profile": root.get("profile"),
    }

    # identity
    ident = root.find(_q("identity"))
    if ident is not None:
        sig = ident.find(_q("signature"))
        data["identity"] = {
            "agreementType": _text(ident, "agreementType"),
            "title": _text(ident, "title"),
            "language": _text(ident, "language"),
            "status": _text(ident, "status"),
            "version": _text(ident, "version"),
            "registrationNo": _text(ident, "registrationNo"),
            "parents": [
                {"id": _text(p, "id"), "relationship": _text(p, "relationship"),
                 "label": _text(p, "label")}
                for p in ident.findall(_q("parent"))
            ],
            "signature": {
                "method": _text(sig, "method"),
                "executedAt": _text(sig, "executedAt"),
                "registrationNo": _text(sig, "registrationNo"),
            } if sig is not None else {},
        }

    # provenance
    prov = root.find(_q("provenance"))
    if prov is not None:
        proc = prov.find(_q("procurement"))
        fs = prov.find(_q("fundingSources"))
        nb = prov.find(_q("normativeBasis"))
        data["provenance"] = {
            "ocid": _text(prov, "ocid"),
            "procurement": {
                "system": _text(proc, "system"),
                "procedureId": _text(proc, "procedureId"),
                "frameworkAgreementId": _text(proc, "frameworkAgreementId"),
                "positionId": _text(proc, "positionId"),
                "orderId": _text(proc, "orderId"),
                "cpv": _texts(proc, "cpv"),
            } if proc is not None else {},
            "fundingSources": [
                {"instrument": _text(f, "instrument"), "projectId": _text(f, "projectId"),
                 "title": _text(f, "title")}
                for f in (fs.findall(_q("fundingSource")) if fs is not None else [])
            ],
            "normativeReferences": [
                {"eli": _text(n, "eli"), "label": _text(n, "label"),
                 "version": _text(n, "version")}
                for n in (nb.findall(_q("normativeReference")) if nb is not None else [])
            ],
        }

    # parties
    parties_el = root.find(_q("parties"))
    parties = []
    if parties_el is not None:
        for p in parties_el.findall(_q("party")):
            bank = p.find(_q("bank"))
            contact = p.find(_q("contact"))
            parties.append({
                "id": _text(p, "id"),
                "roles": _texts(p, "role"),
                "legalName": _text(p, "legalName"),
                "registrationNo": _text(p, "registrationNo"),
                "identifierScheme": _text(p, "identifierScheme"),
                "address": _text(p, "address"),
                "signatory": _text(p, "signatory"),
                "bank": {"name": _text(bank, "name"), "bic": _text(bank, "bic"),
                         "iban": _text(bank, "iban")} if bank is not None else {},
                "contact": {"name": _text(contact, "name"), "email": _text(contact, "email"),
                            "phone": _text(contact, "phone")} if contact is not None else {},
            })
    data["parties"] = parties

    # subject
    subj = root.find(_q("subject"))
    if subj is not None:
        works_el = subj.find(_q("works"))
        data["subject"] = {
            "summary": _text(subj, "summary"),
            "system": _text(subj, "system"),
            "works": [
                {"no": _text(w, "no"), "name": _text(w, "name")}
                for w in (works_el.findall(_q("work")) if works_el is not None else [])
            ],
        }

    # commercials
    com = root.find(_q("commercials"))
    if com is not None:
        pricing_el = com.find(_q("pricing"))
        ceil = com.find(_q("ceiling"))
        pt = com.find(_q("paymentTerms"))
        data["commercials"] = {
            "currency": _text(com, "currency"),
            "vatExcluded": _bool(com, "vatExcluded"),
            "pricing": [
                {"model": _text(l, "model"), "unit": _text(l, "unit"), "rate": _text(l, "rate")}
                for l in (pricing_el.findall(_q("priceLine")) if pricing_el is not None else [])
            ],
            "ceiling": {"unit": _text(ceil, "unit"), "max": _text(ceil, "max")} if ceil is not None else {},
            "paymentTerms": {"daysAfterInvoice": _text(pt, "daysAfterInvoice"),
                             "dayType": _text(pt, "dayType")} if pt is not None else {},
        }

    # terms
    terms_el = root.find(_q("terms"))
    clauses = []
    if terms_el is not None:
        for c in terms_el.findall(_q("clause")):
            cons = c.find(_q("constraints"))
            sl = c.find(_q("sourceLocation"))
            clauses.append({
                "id": _text(c, "id"), "type": _text(c, "type"),
                "bearer": _text(c, "bearer"), "beneficiary": _text(c, "beneficiary"),
                "category": _text(c, "category"), "libraryRef": _text(c, "libraryRef"),
                "heading": _text(c, "heading"), "statement": _text(c, "statement"),
                "trigger": _text(c, "trigger"), "consequence": _text(c, "consequence"),
                "algorithmCardRef": _text(c, "algorithmCardRef"),
                "sourceClause": _text(c, "sourceClause"), "normativeRef": _text(c, "normativeRef"),
                "riskLevel": _text(c, "riskLevel"), "fallbackPosition": _text(c, "fallbackPosition"),
                "negotiability": _text(c, "negotiability"), "ownerDepartment": _text(c, "ownerDepartment"),
                "approvalRequired": _text(c, "approvalRequired"), "jurisdiction": _text(c, "jurisdiction"),
                "mandatoryByLaw": _bool(c, "mandatoryByLaw"),
                "playbookRuleRef": _text(c, "playbookRuleRef"),
                "aiExtractionConfidence": _text(c, "aiExtractionConfidence"),
                "humanReviewedBy": _text(c, "humanReviewedBy"),
                "constraints": {
                    "ratePerDay": _text(cons, "ratePerDay"),
                    "capOfContractValue": _text(cons, "capOfContractValue"),
                    "deadlineValue": _text(cons, "deadlineValue"),
                    "deadlineUnit": _text(cons, "deadlineUnit"),
                } if cons is not None else {},
                "sourceLocation": {
                    "document": _text(sl, "document"), "page": _text(sl, "page"),
                    "paragraph": _text(sl, "paragraph"),
                } if sl is not None else {},
            })
    data["terms"] = clauses

    # serviceLevels
    sl_el = root.find(_q("serviceLevels"))
    if sl_el is not None:
        ts = sl_el.find(_q("ticketingSystem"))
        cals_el = sl_el.find(_q("calendars"))
        classes_el = sl_el.find(_q("classes"))
        data["serviceLevels"] = {
            "ticketingSystem": {
                "type": _text(ts, "type"), "instanceRef": _text(ts, "instanceRef"),
                "workflowIsBinding": _bool(ts, "workflowIsBinding"),
            } if ts is not None else {},
            "calendars": [
                {"id": _text(c, "id"), "hours": _text(c, "hours"), "days": _text(c, "days")}
                for c in (cals_el.findall(_q("calendar")) if cals_el is not None else [])
            ],
            "classes": [_parse_class(k) for k in (classes_el.findall(_q("class")) if classes_el is not None else [])],
        }

    # lifecycle
    lc = root.find(_q("lifecycle"))
    if lc is not None:
        term = lc.find(_q("term"))
        nr = lc.find(_q("noticeRules"))
        data["lifecycle"] = {
            "effectiveFrom": _text(lc, "effectiveFrom"),
            "term": {"max": _text(term, "max"), "unit": _text(term, "unit")} if term is not None else {},
            "amendmentRule": _text(lc, "amendmentRule"),
            "noticeRules": {
                "registeredMailDeemedReceivedDays": _text(nr, "registeredMailDeemedReceivedDays"),
                "electronicDeemedReceivedWorkingDays": _text(nr, "electronicDeemedReceivedWorkingDays"),
            } if nr is not None else {},
            "disputeResolution": _text(lc, "disputeResolution"),
            "governingLaw": _text(lc, "governingLaw"),
        }

    # attachments
    att_el = root.find(_q("attachments"))
    if att_el is not None:
        data["attachments"] = [
            {"id": _text(a, "id"), "title": _text(a, "title"),
             "documentType": _text(a, "documentType"), "uri": _text(a, "uri")}
            for a in att_el.findall(_q("attachment"))
        ]

    return data


def _parse_class(k) -> dict:
    resp = k.find(_q("responseTarget"))
    reso = k.find(_q("resolutionTarget"))
    chans = k.find(_q("channels"))
    return {
        "id": _text(k, "id"), "priority": _text(k, "priority"),
        "label": _text(k, "label"), "calendar": _text(k, "calendar"),
        "responseTarget": {"value": _text(resp, "value"), "unit": _text(resp, "unit"),
                           "note": _text(resp, "note")} if resp is not None else {},
        "resolutionTarget": {"value": _text(reso, "value"), "unit": _text(reso, "unit"),
                             "note": _text(reso, "note")} if reso is not None else {},
        "channels": _texts(chans, "channel"),
        "billing": _text(k, "billing"), "notes": _text(k, "notes"),
    }


# --- derived metrics --------------------------------------------------------

def standardization(data: dict) -> tuple[int, Optional[float]]:
    """(clause_count, standardization_ratio). Ratio = clauses with a
    libraryRef / total clauses. None when there are no clauses."""
    clauses = data.get("terms") or []
    n = len(clauses)
    if n == 0:
        return 0, None
    from_lib = sum(1 for c in clauses if (c.get("libraryRef") or "").strip())
    return n, round(from_lib / n, 3)


def summarize(data: dict) -> dict:
    """Denormalised header fields for the Agreement row."""
    ident = data.get("identity") or {}
    parties = data.get("parties") or []
    def name_for(roles):
        for p in parties:
            if set(p.get("roles") or []) & set(roles):
                return p.get("legalName")
        return None
    n, ratio = standardization(data)
    return {
        "title": ident.get("title"),
        "agreement_type": ident.get("agreementType"),
        "profile": data.get("profile"),
        "language": ident.get("language") or "lv",
        "status": ident.get("status") or "draft",
        "buyer_name": name_for(["buyer", "employer", "lessor", "discloser"]),
        "supplier_name": name_for(["supplier", "employee", "lessee", "recipient"]),
        "clause_count": n,
        "standardization_ratio": ratio,
    }
