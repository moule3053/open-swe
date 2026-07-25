"""Environment configuration for platform services."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    return int(raw)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: (
            _env(
                "DATABASE_URL",
                "postgresql+asyncpg://openswe:openswe@localhost:5432/openswe",
            )
            or ""
        )
    )
    nats_url: str = field(default_factory=lambda: _env("NATS_URL", "nats://localhost:4222") or "")
    token_encryption_key: str | None = field(default_factory=lambda: _env("TOKEN_ENCRYPTION_KEY"))
    # LLM routing: auto | litellm | direct (LiteLLM is optional)
    llm_mode: str = field(default_factory=lambda: _env("LLM_MODE", "auto") or "auto")
    litellm_enabled: bool = field(default_factory=lambda: _env_bool("LITELLM_ENABLED", False))
    litellm_base_url: str = field(default_factory=lambda: _env("LITELLM_BASE_URL", "") or "")
    litellm_api_key: str = field(
        default_factory=lambda: _env("LITELLM_API_KEY", "sk-litellm") or ""
    )
    default_llm_provider: str = field(
        default_factory=lambda: _env("DEFAULT_LLM_PROVIDER", "openai") or "openai"
    )
    openai_api_key: str | None = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_base_url: str = field(
        default_factory=lambda: (
            _env("OPENAI_BASE_URL", "https://api.openai.com/v1") or "https://api.openai.com/v1"
        )
    )
    anthropic_api_key: str | None = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_base_url: str = field(
        default_factory=lambda: (
            _env("ANTHROPIC_BASE_URL", "https://api.anthropic.com") or "https://api.anthropic.com"
        )
    )
    fireworks_api_key: str | None = field(default_factory=lambda: _env("FIREWORKS_API_KEY"))
    fireworks_base_url: str = field(
        default_factory=lambda: (
            _env("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
            or "https://api.fireworks.ai/inference/v1"
        )
    )
    google_api_key: str | None = field(
        default_factory=lambda: _env("GOOGLE_API_KEY") or _env("GEMINI_API_KEY")
    )
    default_model: str = field(
        default_factory=lambda: _env("DEFAULT_MODEL", "openai:gpt-4o-mini") or "openai:gpt-4o-mini"
    )
    default_sandbox_provider: str = field(
        default_factory=lambda: _env("DEFAULT_SANDBOX_PROVIDER", "daytona") or "daytona"
    )
    lease_ttl_seconds: int = field(default_factory=lambda: _env_int("LEASE_TTL_SECONDS", 60))
    heartbeat_interval_seconds: int = field(
        default_factory=lambda: _env_int("HEARTBEAT_INTERVAL_SECONDS", 15)
    )
    max_run_duration_seconds: int = field(
        default_factory=lambda: _env_int("MAX_RUN_DURATION_SECONDS", 4 * 3600)
    )
    max_run_retries: int = field(default_factory=lambda: _env_int("MAX_RUN_RETRIES", 3))
    outbox_poll_interval_seconds: float = field(
        default_factory=lambda: float(_env("OUTBOX_POLL_INTERVAL_SECONDS", "1") or "1")
    )
    api_auth_disabled: bool = field(default_factory=lambda: _env_bool("API_AUTH_DISABLED", True))
    platform_api_token: str | None = field(default_factory=lambda: _env("PLATFORM_API_TOKEN"))
    platform_jwt_secret: str | None = field(default_factory=lambda: _env("PLATFORM_JWT_SECRET"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in (_env("CORS_ORIGINS", "http://localhost:3000") or "").split(",")
            if origin.strip()
        )
    )
    default_org_id: str = field(
        default_factory=lambda: (
            _env("DEFAULT_ORG_ID", "00000000-0000-4000-8000-000000000001")
            or "00000000-0000-4000-8000-000000000001"
        )
    )
    default_user_id: str = field(
        default_factory=lambda: (
            _env("DEFAULT_USER_ID", "00000000-0000-4000-8000-000000000002")
            or "00000000-0000-4000-8000-000000000002"
        )
    )
    github_webhook_secret: str | None = field(default_factory=lambda: _env("GITHUB_WEBHOOK_SECRET"))
    slack_signing_secret: str | None = field(default_factory=lambda: _env("SLACK_SIGNING_SECRET"))
    webhook_signatures_required: bool = field(
        default_factory=lambda: _env_bool("WEBHOOK_SIGNATURES_REQUIRED", False)
    )
    service_name: str = field(
        default_factory=lambda: _env("SERVICE_NAME", "platform") or "platform"
    )
    worker_id: str = field(
        default_factory=lambda: (
            _env("WORKER_ID") or __import__("socket").gethostname() or f"worker-{os.getpid()}"
        )
    )
    daytona_api_key: str | None = field(default_factory=lambda: _env("DAYTONA_API_KEY"))
    allow_stub_sandboxes: bool = field(
        default_factory=lambda: _env_bool("ALLOW_STUB_SANDBOXES", False)
    )
    agent_sandbox_kubeconfig: str | None = field(
        default_factory=lambda: _env("AGENT_SANDBOX_KUBECONFIG")
    )
    opensandbox_base_url: str | None = field(default_factory=lambda: _env("OPENSANDBOX_BASE_URL"))
    opensandbox_api_key: str | None = field(default_factory=lambda: _env("OPENSANDBOX_API_KEY"))
    mcp_stdio_allowed: bool = field(default_factory=lambda: _env_bool("MCP_STDIO_ALLOWED", False))
    mcp_allow_private_networks: bool = field(
        default_factory=lambda: _env_bool("MCP_ALLOW_PRIVATE_NETWORKS", False)
    )
    mcp_tool_timeout_seconds: int = field(
        default_factory=lambda: _env_int("MCP_TOOL_TIMEOUT_SECONDS", 120)
    )
    max_mcp_servers_per_run: int = field(
        default_factory=lambda: _env_int("MAX_MCP_SERVERS_PER_RUN", 10)
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
