from __future__ import annotations

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

_settings = get_settings()
_logger = get_logger(__name__)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(request: Request, bucket: str, per_minute: int | None = None) -> None:
    """Fixed-window per-IP rate limit. Raises 429 when exceeded.

    Fails open if Redis is unreachable — availability over strictness for auth.
    """
    limit = per_minute or _settings.rate_limit_auth_per_minute
    key = f"ratelimit:{bucket}:{_client_ip(request)}"
    try:
        r = await get_redis()
        # Atomic incr + set-TTL-if-absent: avoids a TTL-less key (permanent 429)
        # if the worker dies between INCR and EXPIRE. EXPIRE ... NX needs Redis 7+.
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60, nx=True)
            count, _ = await pipe.execute()
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again in a minute.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        _logger.warning("Rate limiter unavailable (%s), allowing request", exc)


async def register_failed_login(email: str) -> None:
    try:
        r = await get_redis()
        key = f"login_failures:{email.lower()}"
        # Atomic incr + TTL-if-absent so a crashed worker can't leave a permanent
        # (TTL-less) lockout key that no successful login could ever clear.
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, _settings.login_lockout_minutes * 60, nx=True)
            await pipe.execute()
    except Exception as exc:
        _logger.warning("Lockout tracking unavailable: %s", exc)


async def clear_failed_logins(email: str) -> None:
    try:
        r = await get_redis()
        await r.delete(f"login_failures:{email.lower()}")
    except Exception as exc:
        _logger.warning("Lockout tracking unavailable: %s", exc)


async def consume_action_jti(jti: str, ttl_seconds: int) -> bool:
    """Mark a one-time action token (jti) as used.

    Returns True if this is the first use, False if it was already consumed.
    Fails open (returns True) if Redis is unavailable, consistent with the rest
    of the auth path favoring availability.
    """
    if not jti:
        return True
    try:
        r = await get_redis()
        # SET key 1 NX EX ttl -> returns True only the first time.
        was_set = await r.set(f"used_jti:{jti}", "1", nx=True, ex=ttl_seconds)
        return bool(was_set)
    except Exception as exc:
        _logger.warning("Single-use token tracking unavailable: %s", exc)
        return True


async def assert_not_locked_out(email: str) -> None:
    try:
        r = await get_redis()
        count = await r.get(f"login_failures:{email.lower()}")
    except Exception as exc:
        _logger.warning("Lockout tracking unavailable: %s", exc)
        return
    if count is not None and int(count) >= _settings.login_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                f"Account temporarily locked after {_settings.login_max_attempts} failed attempts. "
                f"Try again in {_settings.login_lockout_minutes} minutes or reset your password."
            ),
        )
