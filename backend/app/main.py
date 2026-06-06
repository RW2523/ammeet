from __future__ import annotations

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, get_redis
from app.routers import auth, workspaces, people, meetings, questions, reports, knowledge, integrations, admin
from app.routers import live_session

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

_settings = get_settings()
_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _logger.info("AmMeeting backend starting up")
    # Verify redis
    r = await get_redis()
    await r.ping()
    _logger.info("Redis connected")
    yield
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
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(live_session.router, prefix="/api", tags=["live-session"])


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}
