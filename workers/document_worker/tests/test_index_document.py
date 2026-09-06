import uuid
from unittest.mock import AsyncMock, patch

import pytest
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy import insert, select, text

from app.core.config import settings
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
            await _index_document_async(str(seeded["job_id"]), attempts=1)

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
            await _index_document_async(str(seeded["job_id"]), attempts=1)

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
            await _index_document_async(str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "FAILED"

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "PROCESSING_FAILED"
    finally:
        await _cleanup(seeded)
