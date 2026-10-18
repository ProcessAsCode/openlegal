# intake-zabbix

Standalone adapter service (separate container from the API). Phase 1 deliverable.

See the project README ("Components" and "Jira integration" sections) for the role this adapter plays in the architecture.

## Status

Placeholder. Implementation lands in Phase 1.

## What lands here in Phase 1

- `Dockerfile` — Python 3.12 + httpx + FastAPI
- `main.py` — adapter entry point (intake adapters: webhook receiver or poller; Jira adapters: bidirectional client)
- Normalization layer that maps adapter-specific payloads to OpenLegal's typed signal schema
- Outbound POST to `{OPENLEGAL_BASE_URL}/api/intake/signal` (with X-Trace-Id propagation)
- Health endpoint at `/health`

## Local dev

The `docker-compose.yml` declares this adapter under the `adapters` profile.
To bring up the adapter alongside the API:

```
docker compose --profile adapters up intake-zabbix
```
