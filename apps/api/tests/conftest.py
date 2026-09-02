"""Shared fixtures for the auth/multi-tenant test suite.

Requires `docker compose up -d` to be running (real Postgres, real Redis).
"""

from collections.abc import AsyncGenerator, Callable

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.auth.router import limiter
from app.core.database import engine
from app.main import app

# Rate limiting is a real production concern (see ADR-015) but not what these
# tests exercise, and the shared in-Redis counter would otherwise leak across
# tests hitting /auth/register and /auth/login from the same test-client "IP".
limiter.enabled = False


@pytest_asyncio.fixture(autouse=True)
async def _clean_database() -> AsyncGenerator[None, None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE audit_logs, processing_jobs, document_versions, documents, "
                "knowledge_spaces, organization_members, users, organizations "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture
async def client_factory() -> AsyncGenerator[Callable[[], AsyncClient], None]:
    clients: list[AsyncClient] = []

    def _make() -> AsyncClient:
        transport = ASGITransport(app=app)
        new_client = AsyncClient(transport=transport, base_url="http://test")
        clients.append(new_client)
        return new_client

    yield _make

    for created_client in clients:
        await created_client.aclose()
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(client_factory: Callable[[], AsyncClient]) -> AsyncClient:
    return client_factory()
