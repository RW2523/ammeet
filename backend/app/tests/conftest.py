from __future__ import annotations

import os

# Must be set before app modules import Settings (cached at import time):
# keep the per-IP rate limiter out of the way for the whole suite — the
# dedicated rate-limit test patches the cached Settings instance directly.
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MINUTE", "100000")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User, Workspace, WorkspaceMember, WorkspaceRole
from app.core.security import hash_password

TEST_DB_URL = "postgresql+asyncpg://ammeet:ammeet_secret@localhost:5432/ammeet_test"

# NullPool: pytest-asyncio runs each test in its own event loop, and pooled
# asyncpg connections cannot be reused across loops.
test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        # KnowledgeChunk.embedding uses the pgvector `vector` type, which only
        # exists after the extension is created. conftest builds the schema with
        # create_all (not Alembic), so create the extension here for CI/fresh DBs.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_state():
    """Clear per-IP rate-limit / lockout / single-use state so tests don't bleed
    into each other (endpoints with explicit per_minute limits ignore the global
    high cap)."""
    from app.core.redis import get_redis

    try:
        r = await get_redis()
        for pattern in ("ratelimit:*", "login_failures:*", "used_jti:*", "stripe_event:*"):
            keys = [k async for k in r.scan_iter(pattern)]
            if keys:
                await r.delete(*keys)
    except Exception:
        pass
    yield


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession):
    user = User(
        email="test@ammeet.io",
        hashed_password=hash_password("test1234"),
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_token(client, test_user):
    response = await client.post("/api/auth/login", json={"email": "test@ammeet.io", "password": "test1234"})
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def superuser_token(client, db_session, test_user):
    """A token whose user is a superuser (for instance-admin endpoints like LLM config)."""
    test_user.is_superuser = True
    await db_session.flush()
    response = await client.post("/api/auth/login", json={"email": "test@ammeet.io", "password": "test1234"})
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def test_workspace(db_session: AsyncSession, test_user: User):
    ws = Workspace(name="Test Workspace", slug="test-workspace-1")
    db_session.add(ws)
    await db_session.flush()
    member = WorkspaceMember(workspace_id=ws.id, user_id=test_user.id, role=WorkspaceRole.OWNER)
    db_session.add(member)
    await db_session.flush()
    return ws
