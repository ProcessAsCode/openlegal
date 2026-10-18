# Intake adapters

OpenLegal accepts incident signals through a small set of typed intake adapters.
Each adapter normalizes its source format into the canonical `Signal` schema
and posts to the application API. Adapters run as sidecar containers and can be
enabled selectively per deployment.

| Adapter             | Source                                | Notes                                                |
|---------------------|---------------------------------------|------------------------------------------------------|
| `adapter-zabbix`    | Zabbix server webhooks                | Direct webhook receiver; can be replaced with Prometheus Alertmanager, Datadog, or custom monitoring |
| `adapter-email`     | Email helpdesks (IMAP / Graph)        | Polls a shared mailbox; threads replies back into the case |
| `adapter-jira-dc`   | Self-hosted ticket system (REST v2)   | Bidirectional sync with native webhook receiver       |
| `adapter-jira-cloud`| Cloud ticket system (REST v3)         | Bidirectional sync with webhook relay                 |
| `adapter-cti`       | Telephony / CTI                       | Call-detail records, recording metadata               |

Each adapter is independently deployable and configurable. A deployment runs
only the adapters it needs.

## Adapter contract

Every adapter implements the same outbound contract: HTTP POST to
`/api/intake/` with a body matching the `SignalCreate` schema (source,
external_id, raw_payload, optional normalized_payload). Adapter-specific
authentication credentials and source-system endpoints are configured per
adapter and never leak into the main application API.
