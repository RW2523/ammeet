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

    # Meeting bot — "mock" | "recall"
    bot_provider: Literal["mock", "recall"] = "mock"
    recall_api_key: str = ""
    recall_api_base: str = "https://us-east-1.recall.ai/api/v1"
    # Webhook URL Recall.ai will POST transcripts to (must be publicly reachable)
    webhook_base_url: str = "http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
