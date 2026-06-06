from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import LLMProvider


@lru_cache
def get_llm() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.services.llm.providers import AnthropicProvider
        return AnthropicProvider()
    from app.services.llm.providers import OpenAIProvider
    return OpenAIProvider()
