# lv.example.legal.governance_monitoring

Governance-as-Code UAPF package for contract & corporate-governance
compliance monitoring with a governance calendar / scheduling engine.

- `agreements/` — anonymized sample UAS instances (profile lv.example.legal, JSON, uas_version 0.2)
- `dmn/competence_matrix.json` — the corporate competence matrix as a decision table
- `dmn/obligation_action.json` — obligation state -> action routing (auto vs gated)
- `resources/governance_calendar_rules.yaml` — Cadence-as-Code (Valde/Padome/shareholders)
- `algorithms/` — algorithm cards with embedded tests
- `mock-data/` — mock DOCUS registry + SAP actuals (pilot uses read-only adapters)

All band values, cadences and cutoffs are ILLUSTRATIVE and are replaced with
the organisation's real competence matrix and kartibas rullis data during pilot Discovery.
No real customer data is contained in this package.

UAS spec: https://github.com/UAPFormat/UAS-specification
