from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.llm.base import LLMProvider

_logger = get_logger(__name__)


class OpenAICompatProvider(LLMProvider):
    """One provider for every OpenAI-compatible API.

    Covers OpenAI, OpenRouter, and Google Gemini's OpenAI-compatible endpoint —
    they differ only in base_url, api_key, and model id.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        embedding_model: str = "text-embedding-3-small",
        extra_headers: dict[str, str] | None = None,
        supports_embeddings: bool = True,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"}
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=90.0,
        )
        self._model = model
        self._embedding_model = embedding_model
        self._supports_embeddings = supports_embeddings

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
        if not self._supports_embeddings:
            raise NotImplementedError(
                "This provider does not support embeddings; semantic search falls back to keywords."
            )
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

    async def aclose(self) -> None:
        await self._client.aclose()


# Back-compat alias — older imports referenced OpenAIProvider
OpenAIProvider = OpenAICompatProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=90.0,
        )
        self._model = model

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
        raise NotImplementedError("Anthropic does not provide embeddings. Semantic search falls back to keywords.")

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        text = await self.complete(system + "\n\nRespond ONLY with valid JSON.", user)
        # Models sometimes wrap JSON in ```json fences — strip them.
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("```", 2)[1]
            if stripped.startswith("json"):
                stripped = stripped[4:]
        return json.loads(stripped.strip())

    async def aclose(self) -> None:
        await self._client.aclose()
