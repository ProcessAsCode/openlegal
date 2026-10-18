"""
Canonical UAS serializer.

ONE serializer, in Python, is the single source of truth for producing
e-agreement XML. The browser editor edits a structured `data` dict and
POSTs it; the server serialises here so the byte output always matches
the published XSD element order. Nothing serialises UAS in JavaScript.

`data` shape is documented in app/uas/__init__.py and mirrors the XSD:
each section is a dict / list of dicts whose keys are the XSD element
names. Empty / missing values are simply omitted (every leaf below the
section level is optional in the XSD except where noted).
"""
from __future__ import annotations

from typing import Any
from lxml import etree

NS = "urn:eagreement:0.1"
NSMAP = {None: NS}


def _q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def _sub(parent, tag: str, text: Any = None):
    el = etree.SubElement(parent, _q(tag))
    if text is not None and text != "":
        el.text = _to_text(text)
    return el


def _to_text(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _has(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


# Optional leaf: only emit when present. Order of calls = XSD order.
def _opt(parent, tag: str, value: Any):
    if _has(value):
        _sub(parent, tag, value)


def serialize(data: dict) -> bytes:
    root = etree.Element(_q("eAgreement"), nsmap=NSMAP)
    root.set("version", str(data.get("version") or "0.1"))
    if _has(data.get("profile")):
        root.set("profile", data["profile"])

    _identity(root, data.get("identity") or {})
    if _has(data.get("provenance")):
        _provenance(root, data["provenance"])
    _parties(root, data.get("parties") or [])
    if _has(data.get("subject")):
        _subject(root, data["subject"])
    if _has(data.get("commercials")):
        _commercials(root, data["commercials"])
    if _has(data.get("terms")):
        _terms(root, data["terms"])
    if _has(data.get("serviceLevels")):
        _service_levels(root, data["serviceLevels"])
    if _has(data.get("lifecycle")):
        _lifecycle(root, data["lifecycle"])
    if _has(data.get("attachments")):
        _attachments(root, data["attachments"])

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# --- sections ---------------------------------------------------------------

def _identity(root, d: dict):
    el = etree.SubElement(root, _q("identity"))
    _sub(el, "agreementType", d.get("agreementType") or "standalone_contract")
    _sub(el, "title", d.get("title") or "")
    _sub(el, "language", d.get("language") or "lv")
    _sub(el, "status", d.get("status") or "draft")
    _opt(el, "version", d.get("version"))
    _opt(el, "registrationNo", d.get("registrationNo"))
    for p in d.get("parents") or []:
        ref = etree.SubElement(el, _q("parent"))
        _sub(ref, "id", p.get("id") or "")
        _opt(ref, "relationship", p.get("relationship"))
        _opt(ref, "label", p.get("label"))
    sig = d.get("signature") or {}
    if _has(sig):
        s = etree.SubElement(el, _q("signature"))
        _sub(s, "method", sig.get("method") or "unsigned")
        _opt(s, "executedAt", sig.get("executedAt"))
        _opt(s, "registrationNo", sig.get("registrationNo"))


def _provenance(root, d: dict):
    el = etree.SubElement(root, _q("provenance"))
    _opt(el, "ocid", d.get("ocid"))
    proc = d.get("procurement") or {}
    if _has(proc):
        p = etree.SubElement(el, _q("procurement"))
        _opt(p, "system", proc.get("system"))
        _opt(p, "procedureId", proc.get("procedureId"))
        _opt(p, "frameworkAgreementId", proc.get("frameworkAgreementId"))
        _opt(p, "positionId", proc.get("positionId"))
        _opt(p, "orderId", proc.get("orderId"))
        for cpv in proc.get("cpv") or []:
            _opt(p, "cpv", cpv)
    funds = d.get("fundingSources") or []
    if funds:
        fs = etree.SubElement(el, _q("fundingSources"))
        for f in funds:
            one = etree.SubElement(fs, _q("fundingSource"))
            _opt(one, "instrument", f.get("instrument"))
            _opt(one, "projectId", f.get("projectId"))
            _opt(one, "title", f.get("title"))
    norms = d.get("normativeReferences") or []
    if norms:
        nb = etree.SubElement(el, _q("normativeBasis"))
        for n in norms:
            one = etree.SubElement(nb, _q("normativeReference"))
            _opt(one, "eli", n.get("eli"))
            _sub(one, "label", n.get("label") or "")
            _opt(one, "version", n.get("version"))


def _parties(root, parties: list[dict]):
    el = etree.SubElement(root, _q("parties"))
    for p in parties:
        one = etree.SubElement(el, _q("party"))
        _opt(one, "id", p.get("id"))
        for role in (p.get("roles") or [p.get("role")] if p.get("role") else p.get("roles") or []):
            if _has(role):
                _sub(one, "role", role)
        _opt(one, "legalName", p.get("legalName"))
        _opt(one, "registrationNo", p.get("registrationNo"))
        _opt(one, "identifierScheme", p.get("identifierScheme"))
        _opt(one, "address", p.get("address"))
        _opt(one, "signatory", p.get("signatory"))
        bank = p.get("bank") or {}
        if _has(bank):
            b = etree.SubElement(one, _q("bank"))
            _opt(b, "name", bank.get("name"))
            _opt(b, "bic", bank.get("bic"))
            _opt(b, "iban", bank.get("iban"))
        contact = p.get("contact") or {}
        if _has(contact):
            c = etree.SubElement(one, _q("contact"))
            _opt(c, "name", contact.get("name"))
            _opt(c, "email", contact.get("email"))
            _opt(c, "phone", contact.get("phone"))


def _subject(root, d: dict):
    el = etree.SubElement(root, _q("subject"))
    _opt(el, "summary", d.get("summary"))
    _opt(el, "system", d.get("system"))
    works = d.get("works") or []
    if works:
        w = etree.SubElement(el, _q("works"))
        for item in works:
            one = etree.SubElement(w, _q("work"))
            _opt(one, "no", item.get("no"))
            _sub(one, "name", item.get("name") or "")


def _commercials(root, d: dict):
    el = etree.SubElement(root, _q("commercials"))
    _opt(el, "currency", d.get("currency"))
    if d.get("vatExcluded") is not None and d.get("vatExcluded") != "":
        _sub(el, "vatExcluded", bool(d.get("vatExcluded")))
    pricing = d.get("pricing") or []
    if pricing:
        pr = etree.SubElement(el, _q("pricing"))
        for line in pricing:
            one = etree.SubElement(pr, _q("priceLine"))
            _sub(one, "model", line.get("model") or "time_and_materials")
            _opt(one, "unit", line.get("unit"))
            _opt(one, "rate", line.get("rate"))
    ceil = d.get("ceiling") or {}
    if _has(ceil):
        c = etree.SubElement(el, _q("ceiling"))
        _opt(c, "unit", ceil.get("unit"))
        _opt(c, "max", ceil.get("max"))
    pt = d.get("paymentTerms") or {}
    if _has(pt):
        p = etree.SubElement(el, _q("paymentTerms"))
        _opt(p, "daysAfterInvoice", pt.get("daysAfterInvoice"))
        _opt(p, "dayType", pt.get("dayType"))


_CLAUSE_ORDER = [
    "id", "type", "bearer", "beneficiary", "category", "libraryRef", "heading",
    "statement", "trigger",  # constraints handled separately
    "consequence", "algorithmCardRef", "sourceClause", "normativeRef",
    "riskLevel", "fallbackPosition", "negotiability", "ownerDepartment",
    "approvalRequired", "jurisdiction", "mandatoryByLaw", "playbookRuleRef",
    "aiExtractionConfidence", "humanReviewedBy",  # sourceLocation handled separately
]


def _terms(root, clauses: list[dict]):
    el = etree.SubElement(root, _q("terms"))
    for c in clauses:
        one = etree.SubElement(el, _q("clause"))
        _opt(one, "id", c.get("id"))
        _sub(one, "type", c.get("type") or "obligation")
        for k in ("bearer", "beneficiary", "category", "libraryRef", "heading",
                  "statement", "trigger"):
            _opt(one, k, c.get(k))
        constraints = c.get("constraints") or {}
        if _has(constraints):
            cc = etree.SubElement(one, _q("constraints"))
            _opt(cc, "ratePerDay", constraints.get("ratePerDay"))
            _opt(cc, "capOfContractValue", constraints.get("capOfContractValue"))
            _opt(cc, "deadlineValue", constraints.get("deadlineValue"))
            _opt(cc, "deadlineUnit", constraints.get("deadlineUnit"))
        for k in ("consequence", "algorithmCardRef", "sourceClause", "normativeRef",
                  "riskLevel", "fallbackPosition", "negotiability", "ownerDepartment",
                  "approvalRequired", "jurisdiction"):
            _opt(one, k, c.get(k))
        if c.get("mandatoryByLaw") is not None and c.get("mandatoryByLaw") != "":
            _sub(one, "mandatoryByLaw", bool(c.get("mandatoryByLaw")))
        for k in ("playbookRuleRef", "aiExtractionConfidence", "humanReviewedBy"):
            _opt(one, k, c.get(k))
        sl = c.get("sourceLocation") or {}
        if _has(sl):
            s = etree.SubElement(one, _q("sourceLocation"))
            _opt(s, "document", sl.get("document"))
            _opt(s, "page", sl.get("page"))
            _opt(s, "paragraph", sl.get("paragraph"))


def _service_levels(root, d: dict):
    el = etree.SubElement(root, _q("serviceLevels"))
    ts = d.get("ticketingSystem") or {}
    if _has(ts):
        t = etree.SubElement(el, _q("ticketingSystem"))
        _opt(t, "type", ts.get("type"))
        _opt(t, "instanceRef", ts.get("instanceRef"))
        if ts.get("workflowIsBinding") is not None and ts.get("workflowIsBinding") != "":
            _sub(t, "workflowIsBinding", bool(ts.get("workflowIsBinding")))
    cals = d.get("calendars") or []
    if cals:
        cs = etree.SubElement(el, _q("calendars"))
        for cal in cals:
            one = etree.SubElement(cs, _q("calendar"))
            _sub(one, "id", cal.get("id") or "")
            _opt(one, "hours", cal.get("hours"))
            _opt(one, "days", cal.get("days"))
    classes = d.get("classes") or []
    if classes:
        cls = etree.SubElement(el, _q("classes"))
        for k in classes:
            one = etree.SubElement(cls, _q("class"))
            _sub(one, "id", k.get("id") or "")
            _sub(one, "priority", k.get("priority") if k.get("priority") is not None else 0)
            _opt(one, "label", k.get("label"))
            _opt(one, "calendar", k.get("calendar"))
            _duration(one, "responseTarget", k.get("responseTarget"))
            _duration(one, "resolutionTarget", k.get("resolutionTarget"))
            chans = k.get("channels") or []
            if chans:
                ch = etree.SubElement(one, _q("channels"))
                for c in chans:
                    _sub(ch, "channel", c)
            _opt(one, "billing", k.get("billing"))
            _opt(one, "notes", k.get("notes"))


def _duration(parent, tag: str, d):
    if not _has(d):
        return
    el = etree.SubElement(parent, _q(tag))
    _opt(el, "value", d.get("value"))
    _sub(el, "unit", d.get("unit") or "by_agreement")
    _opt(el, "note", d.get("note"))


def _lifecycle(root, d: dict):
    el = etree.SubElement(root, _q("lifecycle"))
    _opt(el, "effectiveFrom", d.get("effectiveFrom"))
    term = d.get("term") or {}
    if _has(term):
        t = etree.SubElement(el, _q("term"))
        _opt(t, "max", term.get("max"))
        _opt(t, "unit", term.get("unit"))
    _opt(el, "amendmentRule", d.get("amendmentRule"))
    nr = d.get("noticeRules") or {}
    if _has(nr):
        n = etree.SubElement(el, _q("noticeRules"))
        _opt(n, "registeredMailDeemedReceivedDays", nr.get("registeredMailDeemedReceivedDays"))
        _opt(n, "electronicDeemedReceivedWorkingDays", nr.get("electronicDeemedReceivedWorkingDays"))
    _opt(el, "disputeResolution", d.get("disputeResolution"))
    _opt(el, "governingLaw", d.get("governingLaw"))


def _attachments(root, atts: list[dict]):
    el = etree.SubElement(root, _q("attachments"))
    for a in atts:
        one = etree.SubElement(el, _q("attachment"))
        _opt(one, "id", a.get("id"))
        _sub(one, "title", a.get("title") or "")
        _opt(one, "documentType", a.get("documentType"))
        _opt(one, "uri", a.get("uri"))
