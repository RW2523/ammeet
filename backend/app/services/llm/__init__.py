from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm.base import LLMProvider
from app.services.llm.providers import AnthropicProvider, OpenAICompatProvider

_logger = get_logger(__name__)

# ── Provider catalog (drives the settings UI + defaults) ────────────────────

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "anthropic": "https://api.anthropic.com/v1",
}

DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-2.0-flash",
    "openrouter": "openai/gpt-4o",
}

DEFAULT_EMBEDDING_MODELS = {
    "openai": "text-embedding-3-small",
    "gemini": "text-embedding-004",
    "openrouter": "openai/text-embedding-3-small",
    "anthropic": "",  # no embeddings — semantic search falls back to keywords
}

PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini", "o1"],
        "default_base_url": PROVIDER_BASE_URLS["openai"],
        "supports_embeddings": True,
        "key_hint": "sk-...",
    },
    {
        "id": "anthropic",
        "label": "Anthropic (Claude)",
        "default_model": "claude-sonnet-4-6",
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "default_base_url": PROVIDER_BASE_URLS["anthropic"],
        "supports_embeddings": False,
        "key_hint": "sk-ant-...",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_base_url": PROVIDER_BASE_URLS["gemini"],
        "supports_embeddings": True,
        "key_hint": "AIza...",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "default_model": "openai/gpt-4o",
        "models": [
            "openai/gpt-4o",
            "anthropic/claude-3.7-sonnet",
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
        "default_base_url": PROVIDER_BASE_URLS["openrouter"],
        "supports_embeddings": False,
        "key_hint": "sk-or-...",
    },
]

VALID_PROVIDERS = {p["id"] for p in PROVIDER_CATALOG}


# ── Active config (runtime, settable from the UI; env is the fallback) ──────

_active_config: dict[str, Any] | None = None
_provider_cache: dict[str, LLMProvider] = {}


def _env_config() -> dict[str, Any]:
    s = get_settings()
    provider = s.llm_provider if s.llm_provider in VALID_PROVIDERS else "openai"
    api_key = s.anthropic_api_key if provider == "anthropic" else s.openai_api_key
    return {
        "provider": provider,
        "api_key": api_key,
        "model": s.llm_model or DEFAULT_MODELS.get(provider, "gpt-4o"),
        "embedding_model": s.embedding_model or DEFAULT_EMBEDDING_MODELS.get(provider, ""),
        "base_url": None,
    }


def get_active_config() -> dict[str, Any]:
    return _active_config if _active_config is not None else _env_config()


def set_active_config(cfg: dict[str, Any]) -> None:
    """Replace the active LLM config and clear the built-provider cache.

    Old providers hold long-lived httpx clients — close them so they don't leak.
    """
    global _active_config
    old_providers = list(_provider_cache.values())
    _active_config = cfg
    _provider_cache.clear()
    for provider in old_providers:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            continue  # no running loop (sync/test context) — GC closes the client
        loop.create_task(provider.aclose())
    _logger.info("Active LLM config set: provider=%s model=%s", cfg.get("provider"), cfg.get("model"))


async def load_active_config(db) -> None:
    """Load the stored LLM config from the DB into the active config (called at startup)."""
    from sqlalchemy import select

    from app.core.security import decrypt_secret
    from app.models.llm import LLMConfig

    result = await db.execute(select(LLMConfig).where(LLMConfig.id == "global"))
    row = result.scalar_one_or_none()
    if not row:
        return
    api_key = ""
    if row.encrypted_api_key:
        try:
            api_key = decrypt_secret(row.encrypted_api_key)
        except ValueError:
            _logger.warning("Stored LLM API key could not be decrypted; using none")
    set_active_config({
        "provider": row.provider,
        "api_key": api_key,
        "model": row.model,
        "embedding_model": row.embedding_model or DEFAULT_EMBEDDING_MODELS.get(row.provider, ""),
        "base_url": row.base_url or None,
    })


def _signature(cfg: dict[str, Any]) -> str:
    return "|".join([
        str(cfg.get("provider")),
        str(cfg.get("model")),
        str(cfg.get("base_url")),
        str(cfg.get("embedding_model")),
        str(hash(cfg.get("api_key") or "")),
    ])


def _build_provider(cfg: dict[str, Any]) -> LLMProvider:
    provider = cfg.get("provider") or "openai"
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model") or DEFAULT_MODELS.get(provider, "gpt-4o")

    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)

    base_url = cfg.get("base_url") or PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["openai"])
    embedding_model = cfg.get("embedding_model") or DEFAULT_EMBEDDING_MODELS.get(provider, "text-embedding-3-small")
    extra_headers = {"X-Title": "AmMeeting"} if provider == "openrouter" else None
    catalog = next((p for p in PROVIDER_CATALOG if p["id"] == provider), None)
    supports_embeddings = bool(catalog["supports_embeddings"]) if catalog else True
    return OpenAICompatProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        embedding_model=embedding_model,
        extra_headers=extra_headers,
        supports_embeddings=supports_embeddings,
    )


def get_llm() -> LLMProvider:
    """Return the active LLM provider, built from the runtime config (env fallback)."""
    cfg = get_active_config()
    sig = _signature(cfg)
    provider = _provider_cache.get(sig)
    if provider is None:
        provider = _build_provider(cfg)
        _provider_cache[sig] = provider
    return provider
