from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm.base import LLMProvider

_settings = get_settings()
_logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {_settings.openai_api_key}"},
            timeout=90.0,
        )
        self._model = _settings.llm_model
        self._embedding_model = _settings.embedding_model

    async def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        resp = await self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.post(
            "/embeddings",
            json={"model": self._embedding_model, "input": text[:8000]},
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        resp = await self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system + "\n\nRespond ONLY with valid JSON."},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": _settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=90.0,
        )
        self._model = _settings.llm_model

    async def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        resp = await self._client.post(
            "/messages",
            json={
                "model": self._model,
                "max_tokens": 4096,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Anthropic does not provide embeddings. Use OpenAI embedding model.")

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        import json
        text = await self.complete(system + "\n\nRespond ONLY with valid JSON.", user)
        return json.loads(text)
