from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models.user import User, Workspace, WorkspaceMember, WorkspaceRole
from app.core.security import hash_password

TEST_DB_URL = "postgresql+asyncpg://ammeet:ammeet_secret@localhost:5432/ammeet_test"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
async def test_workspace(db_session: AsyncSession, test_user: User):
    ws = Workspace(name="Test Workspace", slug="test-workspace-1")
    db_session.add(ws)
    await db_session.flush()
    member = WorkspaceMember(workspace_id=ws.id, user_id=test_user.id, role=WorkspaceRole.OWNER)
    db_session.add(member)
    await db_session.flush()
    return ws
