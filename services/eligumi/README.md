# e-Līgumi — UAS agreement store (OpenLegal component C5)

Standalone container holding structured agreements in the Universal
Agreement Schema (UAS 0.1): XSD + Schematron validated, append-only
versioned XML on disk and in `agreement_revision`, LLM-assisted import of
docx/pdf/text into UAS.

It is the **source of truth** for agreements in the legal Process-as-Code
pilot. The OpenLegal agent reads it through the read-only JSON API; it never
writes. Humans change agreements through the UI or the import job.

| Surface | Path | Auth |
|---|---|---|
| Workspace UI | `/{tenant}/agreements/...` | HTTP basic (`ELIGUMI_UI_USER`/`_PASSWORD`, optional) |
| Read API | `/api/agreements`, `/api/agreements/{id}[?version=n]`, `/api/agreements/{id}/versions`, `/api/agreements/{id}/v{n}/xml` | `X-Api-Key` (`ELIGUMI_API_KEY`, optional) |
| Health | `/api/health` | none — 503 when DB or store dir is broken |

Environment: `ELIGUMI_TENANT_SLUG` (default `demo`), `APP_DB_PATH`,
`AGREEMENTS_ROOT`, `UAS_ROOT`, and for import `LLM_PROVIDER`
(`anthropic` | `openai_compat`), `LLM_ENDPOINT`, `LLM_API_KEY`, `LLM_MODEL`
(or `ANTHROPIC_API_KEY` + `EAGREEMENT_EXTRACT_MODEL`).

Forked from `rg4444/e_invoice_Latvia` @ d333383 — see `FORK_ORIGIN.md`.
