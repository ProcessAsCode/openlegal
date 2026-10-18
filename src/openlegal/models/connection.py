"""Adapter connection model.

Each adapter (Jira DC, Jira Cloud, Zabbix, email IMAP, ...) has one or more
Connection rows holding its configuration. Secrets are NOT stored in `config`
directly — `config` carries non-secret config (URLs, project keys, sender
addresses) and `secret_ref` points at the secret store entry that holds the
PAT / API token / password.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openlegal.models.base import (
    Base,
    TenantScopedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from openlegal.models.signal import Signal


class ConnectionKind(StrEnum):
    """Adapter family this connection belongs to."""

    JIRA_DC = "jira_dc"
    JIRA_CLOUD = "jira_cloud"
    ZABBIX = "zabbix"
    EMAIL_IMAP = "email_imap"
    EMAIL_SMTP = "email_smtp"
    LDAP = "ldap"
    OPENDMS = "opendms"
    LLM_GATEWAY = "llm_gateway"
    DOCUS_REGISTRY = "docus_registry"
    SAP_ACTUALS = "sap_actuals"
    MS_PURVIEW = "ms_purview"  # Microsoft 365 / Purview Information Protection (MIP) layer


class ConnectionStatus(StrEnum):
    """Observed health of the connection."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    ERROR = "error"
    PAUSED = "paused"


class Connection(Base, UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin):
    """A single configured connection to an external system."""

    __tablename__ = "connections"

    kind: Mapped[ConnectionKind] = mapped_column(
        Enum(ConnectionKind, name="connection_kind", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Non-secret configuration (URLs, project keys, sender addresses, etc.)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Pointer to the secret-store entry holding the credential.
    # Phase 1: a string key into a key-value secret table or env var name.
    # Phase 2: a URI into Vault / Azure Key Vault / etc.
    secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="connection_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ConnectionStatus.ACTIVE,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    signals: Mapped[list["Signal"]] = relationship(back_populates="connection")
