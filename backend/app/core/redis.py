from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_settings = get_settings()

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            _settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def publish_event(channel: str, payload: dict[str, Any]) -> None:
    import json

    r = await get_redis()
    await r.publish(channel, json.dumps(payload))


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
