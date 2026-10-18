"""Application configuration loaded from environment variables.

Everything OpenLegal needs at runtime is declared here. Variables follow the
`OPENLEGAL_` prefix convention (mirroring the OpenDMS pattern).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings object. Instantiated once, exposed as `settings`."""

    model_config = SettingsConfigDict(
        env_prefix="OPENLEGAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Core ---
    ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    BASE_URL: str = "http://api:8002"
    FRONTEND_URL: str = "http://localhost:8080"
    LOG_LEVEL: str = "INFO"

    # --- Database ---
    DB_URL: str = "postgresql+asyncpg://openlegal:openlegal@db:5432/openlegal"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # --- Triage ---
    TRIAGE_AUTO: bool = True

    # --- Cache ---
    REDIS_URL: str = "redis://cache:6379/0"

    # --- Auth ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 480

    # --- Inbound webhook (Jira -> OpenLegal) shared secret ---
    WEBHOOK_SECRET: str = ""

    # --- VeriDocs SDK sidecar ---
    SDK_URL: str = "http://sdk:3101"
    SDK_API_KEY: str = ""
    HOST_DID: str = "did:web:openlegal.local"

    # --- UAPF engine ---
    UAPF_ENABLED: bool = True
    # Engine callbacks to /uapf/host/* don't carry X-Org-Slug; default to this org slug.
    # Single-tenant deployments set this to the only org. Multi-tenant deployments must
    # extend the engine to pass org context per session (e.g. via hostManifest extension).
    UAPF_HOST_DEFAULT_ORG_SLUG: str = "demo"
    UAPF_ENGINE_URL: str = "http://uapf-engine:4000"
    UAPF_ENGINE_AUTH_TOKEN: str = ""
    PROCESSGIT_URL: str = ""

    # --- OpenDMS evidence integration ---
    OPENDMS_ENABLED: bool = True
    OPENDMS_URL: str = "http://opendms-api:8002"
    OPENDMS_ORG_ID: str = ""

    # --- LLM gateway ---
    LLM_PROVIDER: Literal["anthropic", "openai_compat", "sandbox", "local"] = "anthropic"
    LLM_MODEL: str = "claude-haiku-4-5"  # haiku for demo cost; override via env for higher quality
    LLM_ENDPOINT: str = ""  # openai_compat base URL ending in /v1 (sovereign LLM via anonymisation gateway)
    LLM_API_KEY: str = Field(default="", validation_alias="LLM_API_KEY")

    # --- Agent layer ---
    AGENT_MAX_STEPS: int = 12
    AGENT_ALLOWED_CAPABILITIES: str = ""  # comma-separated allow-list; empty = broker default
    ELIGUMI_BASE_URL: str = "http://eligumi:8050"
    ELIGUMI_API_KEY: str = Field(default="", validation_alias="ELIGUMI_API_KEY")

    # LLM provider credentials. Names match .env.example.
    # NOT prefixed with OPENLEGAL_ because they're cross-tool conventions.
    # validation_alias overrides the OPENLEGAL_ env_prefix so these can
    # be read from the conventional non-prefixed env keys (.env.example).
    ANTHROPIC_API_KEY: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    SANDBOX_LLM_TOKEN: str = Field(default="", validation_alias="SANDBOX_LLM_TOKEN")

    # --- Storage ---
    STORAGE_BACKEND: Literal["local", "s3", "azure"] = "local"
    STORAGE_LOCAL_PATH: str = "/data/openlegal/attachments"

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:8080",
            "http://localhost:5173",
        ]
    )


settings = Settings()
