# OpenLegal

[![CI](https://github.com/ProcessAsCode/openlegal/actions/workflows/ci.yml/badge.svg)](https://github.com/ProcessAsCode/openlegal/actions/workflows/ci.yml)

**The open Process-as-Code platform for legal departments** — contract &
corporate-governance compliance monitoring ("Governance-as-Code"), built on the
UAPF / UAS open standards and the proven OpenITSM runtime core.

OpenLegal executes versioned, inspectable UAPF process packages against
agreements stored as structured data (UAS — Universal Agreement Schema), and:

- monitors contract **expiry / renewal windows**, **payments after expiry**,
  and **actual-spend limit thresholds** (ERP actuals vs approved limits);
- evaluates the **corporate competence matrix as a DMN decision table** —
  which Valde / Padome / shareholder approvals a contract or amendment needs;
- runs a **governance calendar & scheduling engine**: deadline-driven
  critical-path computation through real meeting cadences, with
  feasible / infeasible alerts and slack tracking;
- keeps routine items automatic and holds judgement items for **human
  approval** (gated obligations) — nothing irreversible without a person.

## Quick start

    docker compose -p openlegal up -d
    curl http://127.0.0.1:28102/api/health
    curl "http://127.0.0.1:28102/api/legal/schedule/contracts?start=2026-06-10"

Stack: FastAPI + PostgreSQL 16 + Redis + UAPF process engine + React/Vite
frontend (port 28181). Packages live in `uapf-packages/` and are mounted
read-only into the runtime.

## The legal governance pilot package

`uapf-packages/lv.example.legal.governance_monitoring/` — Governance-as-Code
package for contract and corporate-governance compliance monitoring. Sample
data is fully anonymized; the design principle is **share the process, never the
data** — UAPF packages replicate between organizations via ProcessGit, UAS
agreement instances never leave the owning organization's environment.

## Standards

- UAPF (process plane): https://github.com/UAPFormat
- UAS (data plane): https://github.com/UAPFormat/UAS-specification
- Sibling platform (IT service management domain): https://github.com/Algomation-AI/OpenITSM

## License

OpenLegal is free and open-source software under the **GNU Affero General
Public License v3.0 only** (AGPL-3.0-only). See [LICENSE](LICENSE) and
[NOTICE](NOTICE). Copyright Cyberfort SIA.

You may use, study, modify and run it, including in production and on your own
infrastructure. If you offer a modified version to users over a network, you
must make your source code available to them under the same licence.

The UAS schema and rule files under `services/eligumi/uas-data/` are also
available under Apache-2.0, so that agreements encoded in UAS do not depend on
this codebase. See NOTICE.

Part of the Process-as-Code open-source stack: https://github.com/ProcessAsCode
