"""
AI-assisted import: convert agreement prose (extracted from an uploaded
Word/PDF) into a UAS `data` dict.

Per the design this is the FIRST version of import: Claude API does the
extraction; the result is always saved as a *draft* and routed to the
editor for human review (the agreement is flagged needs_review=True and
humanReviewedBy is stamped only when a human saves it). The schema's
aiExtractionConfidence / sourceLocation fields exist precisely so this
step leaves an audit trail.

Transport: uses the `anthropic` SDK if installed, else a direct HTTPS
call via httpx. The API key comes from EAGREEMENT_ANTHROPIC_API_KEY (or
ANTHROPIC_API_KEY). Model is configurable via EAGREEMENT_EXTRACT_MODEL.
"""
from __future__ import annotations

import json
import os
import logging
import re
import time
from typing import Optional

API_KEY_ENVS = ("EAGREEMENT_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
DEFAULT_MODEL = os.getenv("EAGREEMENT_EXTRACT_MODEL", "claude-sonnet-4-6")
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
log = logging.getLogger(__name__)
_TOO_LONG_MSG = (
    "Līgums ir pārāk garš vai sarežģīts vienam AI piegājienam (pārsniegts modeļa "
    "atbildes limits). Sadaliet dokumentu mazākās daļās un importējiet pa daļām, "
    "vai ielīmējiet galvenās sadaļas atsevišķi."
)


class ExtractionError(RuntimeError):
    pass


def _api_key() -> str:
    for env in API_KEY_ENVS:
        v = os.getenv(env)
        if v:
            return v
    raise ExtractionError(
        "Nav konfigurēta Anthropic API atslēga "
        "(EAGREEMENT_ANTHROPIC_API_KEY vai ANTHROPIC_API_KEY)."
    )


SYSTEM_PROMPT = """\
You convert a legal agreement (provided as plain text) into a structured
JSON object conforming to the Universal Agreement Schema (UAS) v0.1 data model.

FIRST decide whether the provided text actually is a legal agreement/contract
(including a draft, annex, amendment, or work order of one). If it is clearly
NOT an agreement — e.g. an invoice, receipt, CV, article, email, marketing
copy, a manual, or unrelated text — return ONLY this object and nothing else:
{"not_agreement": true, "reason": "<one short sentence in the document language>"}

Otherwise, return ONLY a JSON object, no prose, no markdown fences. Shape:

{
  "version": "0.1",
  "profile": "services|nda|employment|procurement.work-order|standalone|...",
  "identity": {"agreementType":"framework_agreement|work_order|standalone_contract|amendment|annex",
               "title": str, "language": "lv|en|...", "status":"draft",
               "version": str?, "registrationNo": str?,
               "signature": {"method":"qes|aes|wet_ink|unsigned"}},
  "parties": [{"id": short-slug, "roles":["buyer|supplier|discloser|recipient|employer|employee|..."],
               "legalName": str, "registrationNo": str?, "address": str?, "signatory": str?,
               "bank": {"name":str?,"bic":str?,"iban":str?}?,
               "contact": {"name":str?,"email":str?,"phone":str?}?}],
  "subject": {"summary": str?, "system": str?, "works":[{"no":str?,"name":str}]},
  "commercials": {"currency":str?, "vatExcluded":bool?,
                  "pricing":[{"model":"time_and_materials|fixed_price|subscription","unit":str?,"rate":number?}],
                  "ceiling":{"unit":str?,"max":number?},
                  "paymentTerms":{"daysAfterInvoice":int?,"dayType":"working|calendar"}},
  "terms": [{"id":short-slug,"type":"obligation|permission|prohibition",
             "bearer": party-id?, "beneficiary": party-id?,
             "category":"ip|confidentiality|warranty|termination|liability|compliance|payment|subcontracting|penalty|data_protection|other",
             "heading": str, "statement": str (the clause meaning in plain words),
             "constraints":{"ratePerDay":number?,"capOfContractValue":number?,"deadlineValue":number?,"deadlineUnit":"work_hour|work_day|calendar_hour|calendar_day|by_agreement"}?,
             "riskLevel":"low|medium|high",
             "aiExtractionConfidence": number 0..1 (your confidence in THIS clause),
             "sourceLocation":{"document":str,"page":str?,"paragraph":str?}}],
  "serviceLevels": {...}?,   # only if the contract has an SLA / priority matrix
  "lifecycle": {"effectiveFrom":str?,"term":{"max":int?,"unit":str?},"amendmentRule":str?,
                "disputeResolution":str?,"governingLaw":str?}
}

Rules:
- bearer/beneficiary MUST be one of the party "id" values you assign.
- Every clause MUST have either a "statement" (plain-language meaning) or be left to a libraryRef later; always provide a statement here.
- Preserve the agreement's original language in title/heading/statement (do NOT translate Latvian to English).
- Set aiExtractionConfidence honestly: lower when the source text was ambiguous.
- Put the source document filename in every clause's sourceLocation.document.
- Do not invent parties, amounts, or obligations not present in the text.
"""


def _call_openai_compat(document_text: str, source_filename: str,
                        model: str) -> str:
    """OpenAI-compatible chat completions (a sovereign LLM behind the anonymisation
    gateway in the sandbox, or any vLLM/Ollama endpoint). Selected with
    LLM_PROVIDER=openai_compat; LLM_ENDPOINT is the base URL (…/v1)."""
    import httpx
    base = os.getenv("LLM_ENDPOINT", "").rstrip("/")
    if not base:
        raise ExtractionError("LLM_PROVIDER=openai_compat, bet LLM_ENDPOINT nav norādīts.")
    key = os.getenv("LLM_API_KEY", "")
    MAX_CHARS = 60000
    if len(document_text) > MAX_CHARS:
        document_text = document_text[:MAX_CHARS] + "\n\n[...text truncated for AI extraction...]"
    payload = {
        "model": model,
        "max_tokens": 16000,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Source document filename: {source_filename}\n\nAgreement text:\n\n{document_text}"},
        ],
    }
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    _t = time.time()
    with httpx.Client(timeout=600) as c:
        r = c.post(f"{base}/chat/completions", headers=headers, json=payload)
        if r.status_code != 200:
            raise ExtractionError(f"LLM API kļūda {r.status_code}: {r.text[:300]}")
        body = r.json()
    choice = (body.get("choices") or [{}])[0]
    log.info("uas.extract openai_compat ok: in=%d chars %.1fs finish=%s",
             len(document_text), time.time() - _t, choice.get("finish_reason"))
    if choice.get("finish_reason") == "length":
        raise ExtractionError(_TOO_LONG_MSG)
    return (choice.get("message") or {}).get("content", "") or ""


def _call_llm(document_text: str, source_filename: str, model: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider in ("openai_compat", "openai", "sandbox"):
        return _call_openai_compat(document_text, source_filename,
                                   os.getenv("LLM_MODEL") or model)
    return _call_anthropic(document_text, source_filename, model)


def _call_anthropic(document_text: str, source_filename: str,
                    model: str) -> str:
    MAX_CHARS = 60000
    if len(document_text) > MAX_CHARS:
        document_text = document_text[:MAX_CHARS] + "\n\n[...text truncated for AI extraction...]"
    user_msg = (
        f"Source document filename: {source_filename}\n\n"
        f"Agreement text:\n\n{document_text}"
    )
    # Prefer the official SDK if present.
    try:
        import anthropic  # type: ignore
        # No SDK auto-retries: a retry on timeout would multiply the wait
        # (default 2 retries => ~3x => minutes). Off the request thread there is
        # no edge timeout, so one generous single attempt is the right behaviour.
        client = anthropic.Anthropic(api_key=_api_key(), max_retries=0, timeout=600.0)
        _t = time.time()
        resp = client.messages.create(
            model=model, max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        out = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        log.info("uas.extract SDK ok: in=%d chars %.1fs out_tokens=%s stop=%s",
                 len(document_text), time.time() - _t,
                 getattr(resp.usage, "output_tokens", "?"), getattr(resp, "stop_reason", "?"))
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ExtractionError(_TOO_LONG_MSG)
        return out
    except ImportError:
        pass

    # Fallback: direct HTTPS via httpx.
    import httpx
    headers = {
        "x-api-key": _api_key(),
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model, "max_tokens": 16000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    with httpx.Client(timeout=600) as c:
        r = c.post(API_URL, headers=headers, json=payload)
        if r.status_code != 200:
            raise ExtractionError(f"Anthropic API kļūda {r.status_code}: {r.text[:300]}")
        body = r.json()
    if body.get("stop_reason") == "max_tokens":
        raise ExtractionError(_TOO_LONG_MSG)
    return "".join(
        blk.get("text", "") for blk in body.get("content", [])
        if blk.get("type") == "text"
    )


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # Strip accidental code fences.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Best effort: grab the outermost {...}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ExtractionError("Modelis neatgrieza derīgu JSON.")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ExtractionError(
                "Neizdevās nolasīt AI atbildi kā JSON (iespējams, atbilde bija "
                "nepilnīga). Mēģiniet vēlreiz vai sadaliet dokumentu mazākās daļās.") from e


def extract(document_text: str, source_filename: str,
            model: Optional[str] = None) -> dict:
    """Returns a UAS `data` dict ready to feed serialize.serialize().
    Always forces status=draft; the caller marks needs_review."""
    if not document_text or not document_text.strip():
        raise ExtractionError("Tukšs dokumenta teksts — nav ko ekstrahēt.")
    raw = _call_llm(document_text, source_filename, model or DEFAULT_MODEL)
    data = _parse_json(raw)
    if data.get("not_agreement"):
        _reason = (data.get("reason") or "").strip()
        raise ExtractionError(
            "Šis dokuments neizskatās pēc līguma"
            + ((": " + _reason) if _reason else ".")
            + " Pārliecinieties, ka augšupielādējat līgumu (vai ielīmējiet tā tekstu).")
    data.setdefault("version", "0.1")
    ident = data.setdefault("identity", {})
    ident["status"] = "draft"  # imported drafts are always draft until reviewed
    # Ensure every clause records its source document.
    for c in data.get("terms") or []:
        sl = c.setdefault("sourceLocation", {})
        sl.setdefault("document", source_filename)
    return data
