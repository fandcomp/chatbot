import uuid
from unittest.mock import AsyncMock, patch

import pytest
import voyageai.error as voyage_errors
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import insert, select, text

from app.core.config import settings
from app.core.redis_client import redis_client
from app.database import (
    async_session_factory,
    document_chunks,
    document_nodes,
    document_regions,
    document_versions,
    processing_jobs,
)
from app.indexing.qdrant_writer import COLLECTION_NAME
from app.tasks import _index_document_async


class _FakeTask:
    """Stands in for Celery's bound task `self` — raising the retry
    exception directly gives the test full control without depending on
    Celery's eager-mode retry semantics. Same shape as
    test_sources_tasks.py's own _FakeTask.
    """

    class _RetrySignal(Exception):
        pass

    def retry(self, exc=None, countdown=None):
        raise self._RetrySignal(str(exc))


async def _seed_document_version_and_job(seeded: dict, status: str = "INDEXING") -> None:
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO document_versions (id, organization_id, document_id, "
                "version_number, file_hash, original_filename, mime_type, size_bytes, "
                "storage_path, status) VALUES (:id, :org_id, :doc_id, 1, 'deadbeef', "
                "'test.pdf', 'application/pdf', 10, 'unused/path.pdf', :status)"
            ),
            {
                "id": seeded["version_id"],
                "org_id": seeded["org_id"],
                "doc_id": seeded["document_id"],
                "status": status,
            },
        )
        await session.execute(
            insert(processing_jobs).values(
                id=seeded["job_id"],
                organization_id=seeded["org_id"],
                document_version_id=seeded["version_id"],
                status="QUEUED",
                attempts=0,
            )
        )
        await session.commit()


async def _seed_region(seeded: dict, region_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            insert(document_regions).values(
                id=region_id,
                organization_id=seeded["org_id"],
                document_version_id=seeded["version_id"],
                region_type="LEGAL_BODY",
                page_start=1,
                page_end=1,
                sequence_number=0,
                confidence=0.9,
            )
        )
        await session.commit()


async def _seed_node(seeded: dict, region_id: uuid.UUID, node_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            insert(document_nodes).values(
                id=node_id,
                organization_id=seeded["org_id"],
                document_version_id=seeded["version_id"],
                region_id=region_id,
                parent_id=None,
                previous_id=None,
                next_id=None,
                node_type="ARTICLE",
                label="Pasal 1",
                title=None,
                number_raw="1",
                number_normalized="1",
                numbering_style=None,
                text="Pasal 1",
                normalized_text=None,
                depth=0,
                sequence_number=0,
                page_start=1,
                page_end=1,
                bounding_box=None,
                confidence=0.9,
                source_provenance={},
                structural_path_json=[{"node_type": "ARTICLE", "label": "Pasal 1", "title": None}],
                structural_path_text="Pasal 1",
                structural_depth=1,
                article_number="1",
            )
        )
        await session.commit()


async def _seed_chunk(seeded: dict, node_id: uuid.UUID, chunk_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            insert(document_chunks).values(
                id=chunk_id,
                organization_id=seeded["org_id"],
                document_id=seeded["document_id"],
                document_version_id=seeded["version_id"],
                source_node_id=node_id,
                parent_chunk_id=None,
                previous_chunk_id=None,
                next_chunk_id=None,
                depth=0,
                sequence_number=0,
                page_start=1,
                page_end=1,
                original_text="Pasal 1\nIsi pasal contoh.",
                contextual_text="Dokumen: test-doc\nPasal 1\nIsi pasal contoh.",
                semantic_summary=None,
                token_count=10,
                structural_path_text="Pasal 1",
            )
        )
        await session.commit()


async def _cleanup(seeded: dict) -> None:
    async with async_session_factory() as session:
        # LAN-M5: a reservation may have created usage_ledger_entries (FK to
        # processing_jobs) and a budgets row (FK to organizations) — both
        # must go before the seeded_document_version fixture's own teardown
        # deletes the job/org, or that teardown hits a FK violation.
        await session.execute(
            text("DELETE FROM usage_ledger_entries WHERE job_id = :job_id"),
            {"job_id": seeded["job_id"]},
        )
        await session.execute(
            text("DELETE FROM budgets WHERE organization_id = :org_id"),
            {"org_id": seeded["org_id"]},
        )
        await session.execute(
            text("DELETE FROM document_chunks WHERE document_version_id = :vid"),
            {"vid": seeded["version_id"]},
        )
        await session.execute(
            text("DELETE FROM document_nodes WHERE document_version_id = :vid"),
            {"vid": seeded["version_id"]},
        )
        await session.execute(
            text("DELETE FROM document_regions WHERE document_version_id = :vid"),
            {"vid": seeded["version_id"]},
        )
        await session.commit()

    client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    if await client.collection_exists(COLLECTION_NAME):
        await client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(seeded["document_id"])),
                    )
                ]
            ),
        )


async def _job_row(job_id) -> dict:
    async with async_session_factory() as session:
        return dict(
            (await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id)))
            .mappings()
            .one()
        )


async def _version_row(version_id) -> dict:
    async with async_session_factory() as session:
        return dict(
            (
                await session.execute(
                    select(document_versions).where(document_versions.c.id == version_id)
                )
            )
            .mappings()
            .one()
        )


@pytest.mark.asyncio
async def test_index_document_embeds_chunks_and_upserts_points_and_marks_active(
    seeded_document_version,
):
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock(return_value=[[0.1] * settings.VOYAGE_EMBEDDING_DIMENSION])

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "SUCCEEDED"

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "ACTIVE"

        client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        point = await client.retrieve(collection_name=COLLECTION_NAME, ids=[str(chunk_id)], with_payload=True)
        assert len(point) == 1
        assert point[0].payload["document_id"] == str(seeded["document_id"])
        # Must reflect the ACTIVE status the version transitions to, not the
        # transient "INDEXING" value that was current when the row was read
        # — otherwise M7's mandatory document_status=ACTIVE retrieval filter
        # would never match any point this task ever upserts.
        assert point[0].payload["document_status"] == "ACTIVE"
        assert point[0].payload["article"] == "1"
    finally:
        await _cleanup(seeded)


async def _seed_prior_active_version(seeded: dict, old_version_id: uuid.UUID) -> None:
    # version_number=0: _seed_document_version_and_job always hardcodes 1 for
    # its own row (shared by many other tests in this file) — this must be
    # some other number to avoid uq_document_version_number, not necessarily
    # a realistic predecessor number.
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO document_versions (id, organization_id, document_id, "
                "version_number, file_hash, original_filename, mime_type, size_bytes, "
                "storage_path, status) VALUES (:id, :org_id, :doc_id, 0, 'oldhash', "
                "'old.pdf', 'application/pdf', 10, 'unused/old.pdf', 'ACTIVE')"
            ),
            {"id": old_version_id, "org_id": seeded["org_id"], "doc_id": seeded["document_id"]},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_index_document_auto_supersedes_previous_active_version(seeded_document_version):
    # M13: a new version reaching ACTIVE must flip the document's previous
    # ACTIVE version to SUPERSEDED and record why (SUPERSEDED_BY).
    seeded = seeded_document_version
    old_version_id = uuid.uuid4()
    await _seed_prior_active_version(seeded, old_version_id)
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock(
        return_value=[[0.1] * settings.VOYAGE_EMBEDDING_DIMENSION]
    )

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        new_version = await _version_row(seeded["version_id"])
        assert new_version["status"] == "ACTIVE"

        old_version = await _version_row(old_version_id)
        assert old_version["status"] == "SUPERSEDED"

        async with async_session_factory() as session:
            relation = (
                (
                    await session.execute(
                        text(
                            "SELECT relation_type FROM document_relations WHERE "
                            "from_document_version_id = :old AND to_document_version_id = :new"
                        ),
                        {"old": old_version_id, "new": seeded["version_id"]},
                    )
                )
                .mappings()
                .one()
            )
        assert relation["relation_type"] == "SUPERSEDED_BY"
    finally:
        await _cleanup(seeded)
        async with async_session_factory() as session:
            await session.execute(
                text("DELETE FROM document_relations WHERE to_document_version_id = :new"),
                {"new": seeded["version_id"]},
            )
            await session.execute(
                text("DELETE FROM document_versions WHERE id = :old"), {"old": old_version_id}
            )
            await session.commit()


@pytest.mark.asyncio
async def test_index_document_invalidates_answer_cache_for_the_organization(
    seeded_document_version,
):
    # ADR-018: a version reaching ACTIVE must clear the org's cached answers
    # so a stale-regulation answer is never served past this point.
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    own_key = f"answer_cache:{seeded['org_id']}:{uuid.uuid4()}:deadbeef"
    other_org_id = uuid.uuid4()
    other_key = f"answer_cache:{other_org_id}:{uuid.uuid4()}:deadbeef"
    await redis_client.set(own_key, "{}")
    await redis_client.set(other_key, "{}")

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock(return_value=[[0.1] * settings.VOYAGE_EMBEDDING_DIMENSION])

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        assert await redis_client.get(own_key) is None
        # Another organization's cached answers must be left untouched.
        assert await redis_client.get(other_key) is not None
    finally:
        await redis_client.delete(own_key, other_key)
        await _cleanup(seeded)


@pytest.mark.asyncio
async def test_index_document_fails_the_job_when_embedding_raises(seeded_document_version):
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock(side_effect=RuntimeError("Voyage API error"))

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "FAILED"

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "PROCESSING_FAILED"
    finally:
        await _cleanup(seeded)


@pytest.mark.asyncio
async def test_index_document_reraises_transient_voyage_errors_instead_of_failing(
    seeded_document_version,
):
    # A rate-limit hit resolves on its own (Voyage's own error message says
    # so) — the job must stay retryable (status PROCESSING, exception
    # propagated for Celery's autoretry_for), never resolved to FAILED on the
    # first hit.
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock(
        side_effect=voyage_errors.RateLimitError("rate limited")
    )

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            with pytest.raises(voyage_errors.RateLimitError):
                await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "PROCESSING"

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "INDEXING"
    finally:
        await _cleanup(seeded)


@pytest.mark.asyncio
async def test_index_document_pauses_on_budget_exceeded_instead_of_failing(
    seeded_document_version, monkeypatch
) -> None:
    # LAN-M5 (addendum §8): a job whose estimated cost exceeds the
    # organization's ingestion budget must pause and retry, never fail
    # outright and never silently proceed. A $0 limit means the first
    # reservation attempt (any positive amount) always exceeds it.
    monkeypatch.setattr(settings, "INGESTION_BUDGET_DEFAULT_USD", 0.0)

    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="INDEXING")
    region_id = uuid.uuid4()
    node_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_node(seeded, region_id, node_id)
    await _seed_chunk(seeded, node_id, chunk_id)

    fake_gateway = AsyncMock()
    fake_gateway.embed_documents = AsyncMock()

    try:
        with patch("app.tasks.EmbeddingGateway", return_value=fake_gateway):
            with pytest.raises(_FakeTask._RetrySignal):
                await _index_document_async(_FakeTask(), str(seeded["job_id"]), attempts=1)

        # Never actually called Voyage — the reservation must be checked
        # before the paid call, not after.
        fake_gateway.embed_documents.assert_not_called()

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "PAUSED_BUDGET"

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "INDEXING"
    finally:
        await _cleanup(seeded)


async def _seed_independent_document_version() -> dict:
    """Same shape as `seeded_document_version`, but self-contained (no
    fixture) — used when a test needs two independent document versions in
    play at once, e.g. to prove the embedding cache (LAN-M3) is shared
    across them rather than being some sort of per-request state.
    """
    org_id = uuid.uuid4()
    space_id = uuid.uuid4()
    document_id = uuid.uuid4()
    seeded = {
        "org_id": org_id,
        "document_id": document_id,
        "version_id": uuid.uuid4(),
        "job_id": uuid.uuid4(),
    }
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO organizations (id, name, slug) VALUES "
                "(:id, 'Worker Test Org 2', :slug)"
            ),
            {"id": org_id, "slug": f"worker-test-2-{org_id}"},
        )
        await session.execute(
            text(
                "INSERT INTO knowledge_spaces (id, organization_id, name) VALUES "
                "(:id, :org_id, 'General')"
            ),
            {"id": space_id, "org_id": org_id},
        )
        await session.execute(
            text(
                "INSERT INTO documents (id, organization_id, knowledge_space_id, title) VALUES "
                "(:id, :org_id, :space_id, 'test-doc-2')"
            ),
            {"id": document_id, "org_id": org_id, "space_id": space_id},
        )
        await session.commit()
    return seeded | {"space_id": space_id}


async def _cleanup_independent_document_version(seeded: dict) -> None:
    await _cleanup(seeded)
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM processing_jobs WHERE document_version_id = :vid"),
            {"vid": seeded["version_id"]},
        )
        await session.execute(
            text("DELETE FROM document_versions WHERE document_id = :did"),
            {"did": seeded["document_id"]},
        )
        await session.execute(
            text("DELETE FROM documents WHERE id = :id"), {"id": seeded["document_id"]}
        )
        await session.execute(
            text("DELETE FROM knowledge_spaces WHERE id = :id"), {"id": seeded["space_id"]}
        )
        await session.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": seeded["org_id"]}
        )
        await session.commit()


@pytest.mark.asyncio
async def test_index_document_reuses_cached_embedding_for_identical_chunk_text_across_versions(
    seeded_document_version,
):
    # LAN-M3 (addendum §5): a second, unrelated document version whose chunk
    # has the exact same contextual_text/embedding config must hit the
    # cache — no second Voyage call at all, not even a smaller one.
    first = seeded_document_version
    await _seed_document_version_and_job(first, status="INDEXING")
    first_region_id, first_node_id, first_chunk_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_region(first, first_region_id)
    await _seed_node(first, first_region_id, first_node_id)
    await _seed_chunk(first, first_node_id, first_chunk_id)

    second = await _seed_independent_document_version()
    try:
        await _seed_document_version_and_job(second, status="INDEXING")
        second_region_id, second_node_id, second_chunk_id = (
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
        )
        await _seed_region(second, second_region_id)
        await _seed_node(second, second_region_id, second_node_id)
        # Identical contextual_text to the first version's chunk (both use
        # `_seed_chunk`'s hardcoded text) — this is the cache hit condition.
        await _seed_chunk(second, second_node_id, second_chunk_id)

        first_gateway = AsyncMock()
        first_gateway.embed_documents = AsyncMock(
            return_value=[[0.1] * settings.VOYAGE_EMBEDDING_DIMENSION]
        )
        with patch("app.tasks.EmbeddingGateway", return_value=first_gateway):
            await _index_document_async(_FakeTask(), str(first["job_id"]), attempts=1)
        first_gateway.embed_documents.assert_called_once()

        second_gateway = AsyncMock()
        second_gateway.embed_documents = AsyncMock()
        with patch("app.tasks.EmbeddingGateway", return_value=second_gateway):
            await _index_document_async(_FakeTask(), str(second["job_id"]), attempts=1)
        second_gateway.embed_documents.assert_not_called()

        second_job = await _job_row(second["job_id"])
        assert second_job["status"] == "SUCCEEDED"

        client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        point = await client.retrieve(
            collection_name=COLLECTION_NAME, ids=[str(second_chunk_id)], with_payload=False
        )
        # The cache-hit path must still write a real point with the cached
        # vector, not skip indexing entirely.
        assert len(point) == 1
    finally:
        await _cleanup(first)
        await _cleanup_independent_document_version(second)
