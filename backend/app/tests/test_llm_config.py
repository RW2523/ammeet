from __future__ import annotations

import pytest

from app.services.llm import (
    DEFAULT_MODELS,
    PROVIDER_CATALOG,
    _build_provider,
    get_active_config,
    get_llm,
    set_active_config,
)
from app.services.llm.providers import AnthropicProvider, OpenAICompatProvider


@pytest.fixture(autouse=True)
def _reset_active_llm_config():
    yield
    import app.services.llm as llm_mod
    llm_mod._active_config = None
    llm_mod._provider_cache.clear()


def test_provider_catalog_has_four_providers():
    ids = {p["id"] for p in PROVIDER_CATALOG}
    assert ids == {"openai", "anthropic", "gemini", "openrouter"}


@pytest.mark.asyncio
async def test_non_embedding_providers_raise_on_embed():
    # OpenRouter / Anthropic don't support embeddings — embed() must raise so callers
    # cleanly fall back to keyword search (instead of issuing a doomed vector query).
    for provider in ("openrouter", "anthropic"):
        llm = _build_provider({"provider": provider, "api_key": "k", "model": None,
                               "embedding_model": None, "base_url": None})
        with pytest.raises(Exception):
            await llm.embed("hello")


@pytest.mark.asyncio
async def test_similarity_search_survives_bad_embedding_dimension(db_session, test_workspace, monkeypatch):
    """A vector query that fails (e.g. embedding dim mismatch) must not poison the
    request transaction — the savepoint rolls it back and keyword search still works."""
    from sqlalchemy import select as _select

    from app.models.knowledge import KnowledgeChunk
    from app.services import knowledge_rag

    chunk = KnowledgeChunk(
        workspace_id=test_workspace.id,
        source_type="transcript",
        chunk_text="John owns the deployment pipeline and it is due Friday",
        chunk_index=0,
    )
    chunk.embedding = [0.001] * 1536  # a valid 1536-dim stored vector (pgvector binds a list)
    db_session.add(chunk)
    await db_session.flush()

    class _BadLLM:
        async def embed(self, text):
            return [0.1, 0.2, 0.3]  # WRONG dimension -> the <=> vector op will error

    monkeypatch.setattr(knowledge_rag, "get_llm", lambda: _BadLLM())

    # Must NOT raise InFailedSQLTransactionError; must fall back to keyword search.
    results = await knowledge_rag.similarity_search(db_session, test_workspace.id, "deployment pipeline owner", limit=5)
    assert any("deployment pipeline" in c.chunk_text for c in results)

    # The transaction must still be usable afterwards.
    await db_session.execute(_select(KnowledgeChunk).where(KnowledgeChunk.workspace_id == test_workspace.id))


@pytest.mark.parametrize(
    "provider,expected_cls,base_substr",
    [
        ("openai", OpenAICompatProvider, "api.openai.com"),
        ("gemini", OpenAICompatProvider, "generativelanguage.googleapis.com"),
        ("openrouter", OpenAICompatProvider, "openrouter.ai"),
        ("anthropic", AnthropicProvider, "anthropic.com"),
    ],
)
def test_build_provider_per_type(provider, expected_cls, base_substr):
    prov = _build_provider({"provider": provider, "api_key": "k", "model": None,
                            "embedding_model": None, "base_url": None})
    assert isinstance(prov, expected_cls)
    assert str(prov._client.base_url).find(base_substr) != -1
    assert prov._model == DEFAULT_MODELS[provider]


def test_base_url_override_respected():
    prov = _build_provider({"provider": "openrouter", "api_key": "k", "model": "x/y",
                            "embedding_model": None, "base_url": "https://my-proxy.local/v1"})
    assert "my-proxy.local" in str(prov._client.base_url)
    assert prov._model == "x/y"


def test_get_llm_caches_until_config_changes():
    set_active_config({"provider": "openai", "api_key": "k1", "model": "gpt-4o",
                       "embedding_model": "text-embedding-3-small", "base_url": None})
    a = get_llm()
    b = get_llm()
    assert a is b  # cached by signature
    set_active_config({"provider": "gemini", "api_key": "k2", "model": "gemini-2.0-flash",
                       "embedding_model": None, "base_url": None})
    c = get_llm()
    assert c is not a
    assert get_active_config()["provider"] == "gemini"


# ── API ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_providers_endpoint(client, auth_token):
    r = await client.get("/api/llm/providers", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["providers"]}
    assert {"openai", "anthropic", "gemini", "openrouter"} <= ids


@pytest.mark.asyncio
async def test_llm_config_requires_superuser(client, auth_token):
    # A normal (non-superuser) user must NOT be able to change the global LLM config
    r = await client.put("/api/llm/config", headers={"Authorization": f"Bearer {auth_token}"},
                         json={"provider": "openai", "model": "gpt-4o", "api_key": "sk-hijack"})
    assert r.status_code == 403
    r = await client.post("/api/llm/test", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_llm_config_set_and_mask(client, superuser_token):
    h = {"Authorization": f"Bearer {superuser_token}"}
    r = await client.put("/api/llm/config", headers=h, json={
        "provider": "openrouter",
        "model": "anthropic/claude-3.7-sonnet",
        "api_key": "sk-or-secret-test-key-1234",
    })
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "openrouter"
    assert r.json()["has_key"] is True

    # GET must never return the raw key — only a masked preview
    r = await client.get("/api/llm/config", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openrouter"
    assert data["model"] == "anthropic/claude-3.7-sonnet"
    assert data["has_key"] is True
    assert data["key_preview"] and "secret" not in (data["key_preview"] or "")
    assert data["key_preview"].endswith("1234")

    # The active runtime config now reflects the new provider
    assert get_active_config()["provider"] == "openrouter"


@pytest.mark.asyncio
async def test_llm_config_keeps_existing_key_when_blank(client, superuser_token):
    h = {"Authorization": f"Bearer {superuser_token}"}
    await client.put("/api/llm/config", headers=h, json={
        "provider": "openai", "model": "gpt-4o", "api_key": "sk-keepme-9999",
    })
    # Update model only, no api_key -> key must persist
    await client.put("/api/llm/config", headers=h, json={"provider": "openai", "model": "gpt-4o-mini"})
    r = await client.get("/api/llm/config", headers=h)
    assert r.json()["has_key"] is True
    assert r.json()["key_preview"].endswith("9999")
    assert r.json()["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_llm_config_rejects_unknown_provider(client, superuser_token):
    r = await client.put("/api/llm/config", headers={"Authorization": f"Bearer {superuser_token}"},
                         json={"provider": "skynet"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_llm_test_endpoint_without_key(client, superuser_token):
    # Reset to a provider with no key -> test returns ok=False gracefully
    set_active_config({"provider": "openai", "api_key": "", "model": "gpt-4o",
                       "embedding_model": "text-embedding-3-small", "base_url": None})
    r = await client.post("/api/llm/test", headers={"Authorization": f"Bearer {superuser_token}"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
