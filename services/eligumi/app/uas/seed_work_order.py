"""
Example IT work order as a conformant UAS instance — the worked demo
seed for the e-Agreement workspace.

Modelled on a public-sector "Darba uzdevums" under an EIS framework
agreement — a Jira-driven ITSM / development-support
contract with a P1–P6 priority/SLA matrix. This exercises the hardest
parts of the schema (service levels, penalty constraints, governance
metadata), which is exactly why it is the demo.

This seed lives ONLY in the platform (data/uas/seed + optionally seeded
into a tenant's store); it is deliberately NOT in the public
UAS-specification repo. Supplier identity, hourly rate and order number
are placeholders, filled when an actual order is issued.

Run as a script to (re)generate data/uas/seed/example-work-order-uas.xml.
"""
from __future__ import annotations


def build() -> dict:
    return {
        "version": "0.1",
        "profile": "procurement.work-order",
        "identity": {
            "agreementType": "work_order",
            "title": "Darba uzdevums (VTP) — IS uzturēšana un attīstība",
            "language": "lv",
            "status": "draft",
            "version": "2025.1",
            "registrationNo": "VTP-PLACEHOLDER",
            "signature": {"method": "qes"},
        },
        "provenance": {
            "procurement": {
                "system": "EIS",
                "frameworkAgreementId": "FRAMEWORK-PLACEHOLDER",
                "orderId": "PLACEHOLDER-ORDER-NO",
                "cpv": ["72250000-2"],
            },
            "fundingSources": [
                {"instrument": "Valsts budžets", "title": "IS uzturēšana"},
            ],
            "normativeReferences": [
                {"label": "Publisko iepirkumu likums"},
            ],
        },
        "parties": [
            {
                "id": "buyer", "roles": ["buyer"],
                "legalName": "Valsts iestāde (piemērs)",
                "registrationNo": "PLACEHOLDER",
                "address": "Rīga",
                "signatory": "Direktors",
            },
            {
                "id": "supplier", "roles": ["supplier"],
                "legalName": "Izpildītājs SIA (placeholder)",
                "registrationNo": "PLACEHOLDER",
                "signatory": "Valdes loceklis",
            },
        ],
        "subject": {
            "summary": ("Informācijas sistēmas uzturēšana, atbalsts un attīstība, "
                        "pieprasījumu apstrāde caur Jira pakalpojumu pārvaldību."),
            "system": "Iestādes informācijas sistēma",
            "works": [
                {"no": "1", "name": "Kļūdu novēršana un incidentu risināšana"},
                {"no": "2", "name": "Konsultācijas un lietotāju atbalsts"},
                {"no": "3", "name": "Sistēmas pilnveidošana pēc pieprasījuma"},
            ],
        },
        "commercials": {
            "currency": "EUR",
            "vatExcluded": True,
            "pricing": [
                {"model": "time_and_materials", "unit": "cilvēkstunda", "rate": "0.00"},
            ],
            "ceiling": {"unit": "cilvēkstunda", "max": "3790"},
            "paymentTerms": {"daysAfterInvoice": 30, "dayType": "calendar"},
        },
        "terms": [
            {
                "id": "c-ip", "type": "obligation", "bearer": "supplier", "beneficiary": "buyer",
                "category": "ip", "libraryRef": "lib.ip.full-transfer@1.0",
                "heading": "Autortiesības un mantiskās tiesības",
                "statement": ("Visas izstrādes rezultātā radītās mantiskās autortiesības "
                              "pāriet Pasūtītājam."),
                "riskLevel": "high", "ownerDepartment": "legal",
                "negotiability": "non_negotiable", "jurisdiction": "LV",
                "mandatoryByLaw": False,
                "aiExtractionConfidence": "0.90",
                "humanReviewedBy": "Juridiskā nodaļa",
                "sourceLocation": {"document": "DU_VTP_2025.docx", "paragraph": "Autortiesības"},
            },
            {
                "id": "c-conf", "type": "obligation", "bearer": "supplier", "beneficiary": "buyer",
                "category": "confidentiality", "libraryRef": "lib.confidentiality.mutual@1.0",
                "heading": "Konfidencialitāte",
                "statement": "Puses apņemas neizpaust konfidenciālo informāciju.",
                "riskLevel": "medium", "ownerDepartment": "legal",
            },
            {
                "id": "c-pen", "type": "obligation", "bearer": "supplier", "beneficiary": "buyer",
                "category": "penalty", "libraryRef": "lib.penalty.late@1.0",
                "heading": "Līgumsods par kavējumu",
                "statement": ("Par saistību izpildes kavējumu Izpildītājs maksā līgumsodu "
                              "0,1% no kavētās summas par katru dienu, nepārsniedzot 10%."),
                "constraints": {"ratePerDay": "0.001", "capOfContractValue": "0.10"},
                "algorithmCardRef": "uapf:card:late-penalty",
                "riskLevel": "high", "ownerDepartment": "legal",
                "negotiability": "business_approval", "approvalRequired": "Juridiskās nodaļas vadītājs",
                "jurisdiction": "LV", "mandatoryByLaw": False,
                "playbookRuleRef": "playbook:remedies/ligumsods#R-01",
                "aiExtractionConfidence": "0.88",
                "humanReviewedBy": "Juridiskā nodaļa",
                "sourceLocation": {"document": "DU_VTP_2025.docx", "paragraph": "Līgumsods"},
            },
        ],
        "serviceLevels": {
            "ticketingSystem": {"type": "jira", "instanceRef": "Buyer Jira",
                                "workflowIsBinding": True},
            "calendars": [
                {"id": "darba_laiks", "hours": "09:00-18:00", "days": "P-Pk"},
                {"id": "24x7", "hours": "00:00-24:00", "days": "P-Sv"},
            ],
            "classes": [
                {"id": "P1", "priority": 1, "label": "kritiska", "calendar": "24x7",
                 "responseTarget": {"value": "1", "unit": "calendar_hour"},
                 "resolutionTarget": {"value": "4", "unit": "calendar_hour"},
                 "channels": ["phone", "jira"]},
                {"id": "P2", "priority": 2, "label": "augsta", "calendar": "darba_laiks",
                 "responseTarget": {"value": "2", "unit": "work_hour"},
                 "resolutionTarget": {"value": "8", "unit": "work_hour"}},
                {"id": "P3", "priority": 3, "label": "vidēja", "calendar": "darba_laiks",
                 "responseTarget": {"value": "4", "unit": "work_hour"},
                 "resolutionTarget": {"value": "3", "unit": "work_day"}},
                {"id": "P4", "priority": 4, "label": "zema", "calendar": "darba_laiks",
                 "responseTarget": {"value": "8", "unit": "work_hour"},
                 "resolutionTarget": {"value": "10", "unit": "work_day"}},
                {"id": "P5", "priority": 5, "label": "konsultācija", "calendar": "darba_laiks",
                 "responseTarget": {"value": "2", "unit": "work_day"},
                 "resolutionTarget": {"unit": "by_agreement"}},
                {"id": "P6", "priority": 6, "label": "izmaiņu pieprasījums", "calendar": "darba_laiks",
                 "responseTarget": {"value": "5", "unit": "work_day"},
                 "resolutionTarget": {"unit": "by_agreement"}},
            ],
        },
        "lifecycle": {
            "effectiveFrom": "on_signature",
            "term": {"max": 12, "unit": "month"},
            "amendmentRule": "bilateral_written_only",
            "noticeRules": {"registeredMailDeemedReceivedDays": 7,
                            "electronicDeemedReceivedWorkingDays": 2},
            "disputeResolution": "negotiation_then_courts",
            "governingLaw": "LV",
        },
        "attachments": [
            {"id": "annex-sla", "title": "Pakalpojuma līmeņa pielikums (SLA)",
             "documentType": "serviceLevelAgreement"},
        ],
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from uas import serialize  # noqa
    xml = serialize.serialize(build())
    out = Path(__file__).resolve().parents[2] / "data" / "uas" / "seed" / "example-work-order-uas.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(xml)
    print(f"wrote {out} ({len(xml)} bytes)")
