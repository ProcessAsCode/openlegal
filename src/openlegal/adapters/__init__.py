"""External-system adapter clients used from inside the API process.

Note: this package holds *in-process clients* the API uses to talk to external
systems (Jira REST clients, Zabbix API client, email connectors). The standalone
adapter *services* (which run as separate containers and accept inbound webhooks)
live in the top-level `adapters/` directory of the repo, not here.
"""
