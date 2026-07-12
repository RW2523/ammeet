from __future__ import annotations

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, get_redis
from app.routers import auth, workspaces, people, meetings, questions, reports, knowledge, integrations, admin
from app.routers import billing as billing_router
from app.routers import llm as llm_router
from app.routers import notetaker as notetaker_router
from app.routers import speak as speak_router
from app.routers import public as public_router
from app.routers import live_session

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

_settings = get_settings()
_logger = get_logger(__name__)

if _settings.sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=_settings.sentry_dsn, environment=_settings.environment, traces_sample_rate=0.1)
        _logger.info("Sentry initialized")
    except ImportError:
        _logger.warning("SENTRY_DSN set but sentry-sdk not installed; skipping")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _logger.info("AmMeeting backend starting up")
    # Verify redis
    r = await get_redis()
    await r.ping()
    _logger.info("Redis connected")

    # Load the saved LLM provider config (if any) into the active runtime config
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.llm import load_active_config

        async with AsyncSessionLocal() as _db:
            await load_active_config(_db)
    except Exception as exc:
        _logger.warning("Could not load saved LLM config: %s", exc)

    # Start the auto-join scheduler (deploys the proxy bot at meeting start time)
    background_tasks = []
    if _settings.auto_join_scheduler_enabled:
        from app.services.scheduler import auto_join_loop

        background_tasks.append(asyncio.create_task(auto_join_loop()))

    # Optional: periodically pull connected calendars into auto-join meetings
    if _settings.calendar_auto_sync_enabled:
        from app.services.calendar_sync import calendar_sync_loop

        background_tasks.append(asyncio.create_task(calendar_sync_loop()))

    yield

    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    await close_redis()
    await engine.dispose()
    _logger.info("AmMeeting backend shut down")


app = FastAPI(
    title="AmMeeting API",
    version="1.0.0",
    description="The AI meeting assistant that knows what to ask, collects the answers, and keeps work moving.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(people.router, prefix="/api/workspaces", tags=["people"])
app.include_router(meetings.router, prefix="/api/workspaces", tags=["meetings"])
app.include_router(questions.router, prefix="/api/workspaces", tags=["questions"])
app.include_router(reports.router, prefix="/api/workspaces", tags=["reports"])
app.include_router(knowledge.router, prefix="/api/workspaces", tags=["knowledge"])
app.include_router(integrations.router, prefix="/api/workspaces", tags=["integrations"])
app.include_router(integrations.oauth_router, prefix="/api/integrations", tags=["integrations"])
app.include_router(billing_router.router, prefix="/api/workspaces", tags=["billing"])
app.include_router(billing_router.webhook_router, prefix="/api/billing", tags=["billing"])
app.include_router(llm_router.router, prefix="/api/llm", tags=["llm"])
app.include_router(notetaker_router.router, prefix="/api/workspaces", tags=["notetaker"])
app.include_router(speak_router.router, prefix="/api/workspaces", tags=["speak"])
app.include_router(public_router.router, prefix="/api/public", tags=["public"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(live_session.router, prefix="/api", tags=["live-session"])


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}
