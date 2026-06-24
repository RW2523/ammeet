from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_settings = get_settings()

# One pool per event loop — connections cannot be shared across loops
# (matters under pytest-asyncio, which runs each test in its own loop).
_redis_pools: dict[int, aioredis.Redis] = {}


async def get_redis() -> aioredis.Redis:
    loop_id = id(asyncio.get_running_loop())
    pool = _redis_pools.get(loop_id)
    if pool is None:
        pool = aioredis.from_url(
            _settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        _redis_pools[loop_id] = pool
    return pool


async def publish_event(channel: str, payload: dict[str, Any]) -> None:
    import json

    r = await get_redis()
    await r.publish(channel, json.dumps(payload))


async def close_redis() -> None:
    loop_id = id(asyncio.get_running_loop())
    pool = _redis_pools.pop(loop_id, None)
    if pool:
        await pool.aclose()
