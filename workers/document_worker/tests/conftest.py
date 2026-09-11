"""Requires `docker compose up -d` (real Postgres + MinIO), and apps/api's
migrations already applied (this project has no migrations of its own —
it reads the schema apps/api owns)."""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text

from app.database import engine


@pytest_asyncio.fixture(autouse=True)
async def _clear_embedding_cache() -> AsyncGenerator[None, None]:
    """The embedding cache (LAN-M3, addendum §5) is deliberately global, not
    org-scoped — so it survives `seeded_document_version`'s per-test teardown
    below. Tests that reuse the same literal chunk text across runs would
    otherwise see cache hits leak between them (e.g. a test asserting
    `embed_documents` was called would flake once a prior test's row cached
    that exact text/config). Cleared after every test, not just LAN-M3's own.
    """
    yield
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM embedding_cache_entries"))


@pytest_asyncio.fixture
async def seeded_document_version() -> AsyncGenerator[dict, None]:
    org_id = uuid.uuid4()
    space_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES "
                "(:id, 'Worker Test Org', :slug)"
            ),
            {"id": org_id, "slug": f"worker-test-{org_id}"},
        )
        await conn.execute(
            text(
                "INSERT INTO knowledge_spaces (id, organization_id, name) VALUES "
                "(:id, :org_id, 'General')"
            ),
            {"id": space_id, "org_id": org_id},
        )
        await conn.execute(
            text(
                "INSERT INTO documents (id, organization_id, knowledge_space_id, title) VALUES "
                "(:id, :org_id, :space_id, 'test-doc')"
            ),
            {"id": document_id, "org_id": org_id, "space_id": space_id},
        )

    yield {
        "org_id": org_id,
        "document_id": document_id,
        "version_id": version_id,
        "job_id": job_id,
    }

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM processing_jobs WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        await conn.execute(
            text("DELETE FROM document_versions WHERE document_id = :did"), {"did": document_id}
        )
        await conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})
        await conn.execute(text("DELETE FROM knowledge_spaces WHERE id = :id"), {"id": space_id})
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})
