# Sandbox pilot bundle — Process-as-Code legal POC

Brings up the whole pilot as one stack behind a single port:

```
edge (nginx)  →  frontend        OpenLegal SPA
              →  api             agent + UAPF host   (/api, /uapf)
              →  eligumi         UAS agreement store (/eligumi)
     api      →  uapf-engine     process execution
     api      →  db, cache
     api      →  LLM             via an anonymisation gateway (openai_compat)
```

```bash
cp .env.sandbox.example .env          # fill in the LLM and store secrets
docker compose -p openlegal \
  -f docker-compose.yml \
  -f deploy/sandbox/docker-compose.sandbox.yml up -d
curl -fsS localhost:28100/api/health | jq .status      # "ok" or 503
curl -fsS localhost:28100/eligumi/api/health | jq .ok
```

## Data boundary

Agreements live only in the `openlegal-eligumi-data` volume (UAS XML +
SQLite) and, as a derived view, in `legal_agreements` in Postgres. Deleting
the pilot is deleting those two volumes. No component calls a public model
provider: with `LLM_PROVIDER=openai_compat` every completion goes to
`LLM_ENDPOINT`, which is the anonymisation gateway.

## Verifying the two failure modes that hurt before

Both are documented in the operator's runbook and are the reason the edge and the
healthchecks look the way they do.

1. **Pinned upstream IP.** Stop `api`, squat its old address with a throwaway
   container, recreate `api` so it must take a different one, then curl the
   public URL *without touching the edge*. It must stay 200 and keep the query
   string.
2. **Healthcheck that cannot fail.** Stop `db` and curl `/api/health`: it must
   return 503, not `{"status":"ok"}`.
