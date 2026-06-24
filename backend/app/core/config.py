from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # app
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # database
    database_url: str = "postgresql+asyncpg://ammeet:ammeet_secret@localhost:5432/ammeet"

    # redis
    redis_url: str = "redis://localhost:6379/0"

    # security
    secret_key: str = "change-me-to-a-long-random-string-at-least-64-chars"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # llm
    llm_provider: Literal["openai", "anthropic"] = "openai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"

    # storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./uploads"
    aws_s3_bucket: str = ""
    aws_region: str = "us-east-1"

    # integrations
    jira_provider: Literal["mock", "real"] = "mock"
    calendar_provider: Literal["mock", "real"] = "mock"
    slack_provider: Literal["mock", "real"] = "mock"

    # STT — "mock" | "whisper" | "assemblyai"
    stt_provider: Literal["mock", "whisper", "assemblyai"] = "mock"
    assemblyai_api_key: str = ""

    # TTS — "none" | "openai"
    tts_provider: Literal["none", "openai"] = "openai"
    tts_voice: str = "nova"  # nova | alloy | echo | fable | onyx | shimmer

    # Meeting bot — "mock" | "recall" | "browser" (self-hosted headless-browser bot)
    bot_provider: Literal["mock", "recall", "browser"] = "mock"
    recall_api_key: str = ""
    recall_api_base: str = "https://us-east-1.recall.ai/api/v1"
    # Self-hosted bot-worker (Playwright) URL — used when bot_provider="browser"
    browser_bot_worker_url: str = "http://localhost:4500"
    # Webhook URL Recall.ai will POST transcripts to (must be publicly reachable)
    webhook_base_url: str = "http://localhost:8000"

    # Frontend base URL — used in OAuth redirects and email links
    frontend_url: str = "http://localhost:3000"

    # Auth hardening
    password_min_length: int = 10
    login_max_attempts: int = 5          # failed attempts before lockout
    login_lockout_minutes: int = 15
    rate_limit_auth_per_minute: int = 10  # per-IP cap on auth endpoints
    require_email_verification: bool = False  # flip on in production once SMTP is set

    # Encryption key for integration tokens at rest (Fernet, urlsafe base64, 32 bytes).
    # Empty -> derived from secret_key (fine for dev, set explicitly in production).
    token_encryption_key: str = ""

    # Email — "console" logs emails instead of sending
    email_provider: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "AmMeeting <no-reply@ammeet.io>"
    smtp_use_tls: bool = True

    # Billing — Stripe. Empty keys -> mock billing (everything behaves as free plan
    # with generous limits so dev/demo is unaffected).
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro_monthly: str = ""   # Stripe Price ID for Pro
    stripe_price_team_monthly: str = ""  # Stripe Price ID for Team

    # OAuth client credentials — empty -> provider stays in mock mode
    google_client_id: str = ""
    google_client_secret: str = ""
    slack_client_id: str = ""
    slack_client_secret: str = ""
    jira_client_id: str = ""
    jira_client_secret: str = ""
    # Microsoft (Teams / Microsoft 365) — Azure AD app registration
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"  # "common" | "organizations" | a tenant id

    # Observability
    sentry_dsn: str = ""

    # Auto-join scheduler — background worker deploys the proxy bot at meeting start time
    auto_join_scheduler_enabled: bool = True
    auto_join_poll_seconds: int = 60
    # How early/late (minutes) around scheduled_at the bot may auto-join
    auto_join_lead_minutes: int = 2
    auto_join_grace_minutes: int = 5

    # Calendar auto-sync — background sweep that turns connected-calendar events with
    # join links into auto-join meetings. Off by default (opt-in: it auto-attends).
    calendar_auto_sync_enabled: bool = False
    calendar_auto_sync_minutes: int = 15

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
