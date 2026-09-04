import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select, text

from app.database import (
    async_session_factory,
    document_chunks,
    document_nodes,
    document_regions,
    document_versions,
    processing_jobs,
)
from app.tasks import _chunk_document_async


async def _seed_document_version_and_job(seeded: dict, status: str = "APPROVED") -> None:
    # `seeded_document_version` (conftest.py) already inserted the `documents`
    # row (title 'test-doc') — this only adds the version + job.
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
                region_type="FREEFORM_SECTION",
                page_start=1,
                page_end=1,
                sequence_number=0,
                confidence=0.9,
            )
        )
        await session.commit()


def _node_values(seeded: dict, region_id: uuid.UUID, **overrides) -> dict:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=seeded["org_id"],
        document_version_id=seeded["version_id"],
        region_id=region_id,
        parent_id=None,
        previous_id=None,
        next_id=None,
        node_type="ARTICLE",
        label="Pasal 1",
        title=None,
        number_raw=None,
        number_normalized=None,
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
    )
    defaults.update(overrides)
    return defaults


async def _seed_nodes(rows: list[dict]) -> None:
    async with async_session_factory() as session:
        await session.execute(insert(document_nodes), rows)
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


async def _chunk_rows(version_id) -> list[dict]:
    async with async_session_factory() as session:
        return [
            dict(row)
            for row in (
                await session.execute(
                    select(document_chunks).where(
                        document_chunks.c.document_version_id == version_id
                    )
                )
            )
            .mappings()
            .all()
        ]


@pytest.mark.asyncio
async def test_chunk_document_persists_chunks_and_marks_job_succeeded(
    seeded_document_version,
):
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="APPROVED")
    region_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    article = _node_values(seeded, region_id)
    body = _node_values(
        seeded,
        region_id,
        id=uuid.uuid4(),
        parent_id=article["id"],
        node_type="PARAGRAPH",
        label=None,
        text="Isi pasal contoh.",
        depth=1,
        sequence_number=0,
        structural_path_json=[
            {"node_type": "ARTICLE", "label": "Pasal 1", "title": None},
            {"node_type": "PARAGRAPH", "label": None, "title": None},
        ],
        structural_path_text="Pasal 1 > Isi pasal contoh.",
        structural_depth=2,
    )
    await _seed_nodes([article, body])

    try:
        with patch("app.tasks.index_document.delay") as mock_delay:
            await _chunk_document_async(str(seeded["job_id"]), attempts=1)

        # Chunking never marks the job SUCCEEDED itself anymore — it chains
        # into index_document (M6) under the SAME job row, mirroring
        # M2->M3->M4's pattern (no human-approval gate sits in between).
        job = await _job_row(seeded["job_id"])
        assert job["status"] == "PROCESSING"
        mock_delay.assert_called_once_with(str(seeded["job_id"]))

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "INDEXING"

        chunks = await _chunk_rows(seeded["version_id"])
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk["original_text"] == "Pasal 1\nIsi pasal contoh."
        assert "test-doc" in chunk["contextual_text"]
        assert chunk["document_id"] == seeded["document_id"]
        assert chunk["organization_id"] == seeded["org_id"]
    finally:
        await _cleanup(seeded)


@pytest.mark.asyncio
async def test_chunk_document_links_siblings_via_previous_and_next(seeded_document_version):
    seeded = seeded_document_version
    await _seed_document_version_and_job(seeded, status="APPROVED")
    region_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    section_1 = _node_values(
        seeded,
        region_id,
        node_type="NUMBERED_SECTION",
        label="1. Pertama",
        text="1. Pertama",
        sequence_number=0,
        structural_path_json=[{"node_type": "NUMBERED_SECTION", "label": "1. Pertama", "title": None}],
        structural_path_text="1. Pertama",
    )
    section_2 = _node_values(
        seeded,
        region_id,
        id=uuid.uuid4(),
        node_type="NUMBERED_SECTION",
        label="2. Kedua",
        text="2. Kedua",
        sequence_number=1,
        structural_path_json=[{"node_type": "NUMBERED_SECTION", "label": "2. Kedua", "title": None}],
        structural_path_text="2. Kedua",
    )
    await _seed_nodes([section_1, section_2])

    try:
        with patch("app.tasks.index_document.delay"):
            await _chunk_document_async(str(seeded["job_id"]), attempts=1)

        chunks = sorted(await _chunk_rows(seeded["version_id"]), key=lambda c: c["sequence_number"])
        assert len(chunks) == 2
        assert chunks[0]["next_chunk_id"] == chunks[1]["id"]
        assert chunks[1]["previous_chunk_id"] == chunks[0]["id"]
    finally:
        await _cleanup(seeded)
