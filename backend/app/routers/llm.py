from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_superuser
from app.core.security import decrypt_secret, encrypt_secret
from app.models.llm import LLMConfig
from app.models.user import AuditLog, User
from app.services.llm import (
    DEFAULT_EMBEDDING_MODELS,
    DEFAULT_MODELS,
    PROVIDER_CATALOG,
    VALID_PROVIDERS,
    get_active_config,
    get_llm,
    set_active_config,
)

router = APIRouter()


class LLMConfigUpdate(BaseModel):
    provider: str
    model: str | None = None
    # Omit or send empty to keep the existing stored key.
    api_key: str | None = None
    embedding_model: str | None = None
    base_url: str | None = None


def _mask(key: str | None) -> str | None:
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) >= 4 else "••••"


@router.get("/providers")
async def list_providers(user: User = Depends(get_current_user)) -> dict:
    """Catalog of supported providers + suggested models (drives the settings UI)."""
    return {"providers": PROVIDER_CATALOG}


@router.get("/config")
async def get_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == "global"))
    row = result.scalar_one_or_none()
    active = get_active_config()

    has_key = bool(row.encrypted_api_key) if row else bool(active.get("api_key"))
    key_preview = None
    if row and row.encrypted_api_key:
        try:
            key_preview = _mask(decrypt_secret(row.encrypted_api_key))
        except ValueError:
            key_preview = "••••"
    elif active.get("api_key"):
        key_preview = _mask(active.get("api_key"))

    return {
        "provider": (row.provider if row else active.get("provider")),
        "model": (row.model if row else active.get("model")),
        "embedding_model": (row.embedding_model if row else active.get("embedding_model")),
        "base_url": (row.base_url if row else active.get("base_url")),
        "has_key": has_key,
        "key_preview": key_preview,
        "source": "saved" if row else "env",
    }


@router.put("/config")
async def update_config(
    body: LLMConfigUpdate,
    user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{body.provider}'")

    result = await db.execute(select(LLMConfig).where(LLMConfig.id == "global"))
    row = result.scalar_one_or_none()
    if not row:
        row = LLMConfig(id="global")
        db.add(row)

    row.provider = body.provider
    row.model = body.model or DEFAULT_MODELS.get(body.provider, "gpt-4o")
    row.embedding_model = body.embedding_model or DEFAULT_EMBEDDING_MODELS.get(body.provider, "")
    row.base_url = body.base_url or None

    # Update the key only when a new non-empty one is supplied; otherwise keep it.
    if body.api_key:
        row.encrypted_api_key = encrypt_secret(body.api_key)

    await db.flush()

    # Resolve the plaintext key for the active in-process config
    plaintext_key = ""
    if body.api_key:
        plaintext_key = body.api_key
    elif row.encrypted_api_key:
        try:
            plaintext_key = decrypt_secret(row.encrypted_api_key)
        except ValueError:
            plaintext_key = ""

    set_active_config({
        "provider": row.provider,
        "api_key": plaintext_key,
        "model": row.model,
        "embedding_model": row.embedding_model,
        "base_url": row.base_url,
    })

    db.add(AuditLog(
        user_id=user.id,
        action="llm.config_updated",
        resource_type="llm_config",
        detail=f"{row.provider}:{row.model}",
    ))
    await db.flush()

    return {
        "provider": row.provider,
        "model": row.model,
        "embedding_model": row.embedding_model,
        "base_url": row.base_url,
        "has_key": bool(row.encrypted_api_key),
    }


@router.post("/test")
async def test_config(user: User = Depends(require_superuser)) -> dict:
    """Send a tiny prompt to the active provider to confirm the key/model work."""
    cfg = get_active_config()
    if not cfg.get("api_key"):
        return {"ok": False, "error": "No API key configured for this provider."}
    try:
        llm = get_llm()
        reply = await llm.complete(
            "You are a connectivity test. Reply with a single short word.",
            "Reply with the word: ok",
            temperature=0.0,
        )
        return {"ok": True, "provider": cfg.get("provider"), "model": cfg.get("model"), "sample": reply.strip()[:120]}
    except Exception as exc:  # noqa: BLE001
        detail = str(exc)
        if hasattr(exc, "response") and getattr(exc, "response", None) is not None:
            try:
                detail = f"{exc.response.status_code}: {exc.response.text[:300]}"  # type: ignore[attr-defined]
            except Exception:
                pass
        return {"ok": False, "provider": cfg.get("provider"), "model": cfg.get("model"), "error": detail[:400]}
