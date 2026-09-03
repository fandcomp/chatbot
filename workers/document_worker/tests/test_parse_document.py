import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select, text

from app.core.config import settings
from app.database import (
    async_session_factory,
    document_nodes,
    document_regions,
    document_versions,
    processing_jobs,
)
from app.parsing.docling_adapter import ParserLevel
from app.parsing.pipeline import PipelineResult
from app.parsing.region_segmenter import RegionRecord
from app.parsing.tree_builder import NodeSpec
from app.storage import _client
from app.tasks import _parse_document_async
from tests.fixtures import digital_text_pdf


def _put_test_object(key: str, content: bytes) -> None:
    _client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content)


async def _seed_version_and_job(seeded: dict, storage_path: str, content: bytes) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO document_versions (id, organization_id, document_id, "
                "version_number, file_hash, original_filename, mime_type, size_bytes, "
                "storage_path, status) VALUES (:id, :org_id, :doc_id, 1, 'deadbeef', "
                "'test.pdf', 'application/pdf', :size, :path, 'PROCESSING')"
            ),
            {
                "id": seeded["version_id"],
                "org_id": seeded["org_id"],
                "doc_id": seeded["document_id"],
                "size": len(content),
                "path": storage_path,
            },
        )
        await session.execute(
            insert(processing_jobs).values(
                id=seeded["job_id"],
                organization_id=seeded["org_id"],
                document_version_id=seeded["version_id"],
                status="PROCESSING",
                attempts=0,
            )
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


async def _cleanup_parsing_rows(version_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM document_nodes WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        await session.execute(
            text("DELETE FROM document_regions WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        await session.commit()


@pytest.mark.asyncio
async def test_parse_document_persists_regions_and_nodes_and_marks_version_parsed(
    seeded_document_version,
):
    seeded = seeded_document_version
    content = digital_text_pdf()
    storage_path = (
        f"organization/{seeded['org_id']}/documents/{seeded['document_id']}/"
        f"versions/{seeded['version_id']}/original/test.pdf"
    )
    _put_test_object(storage_path, content)
    await _seed_version_and_job(seeded, storage_path, content)

    try:
        await _parse_document_async(str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "SUCCEEDED"

        version = await _version_row(seeded["version_id"])
        assert version["status"] in ("PARSED", "REVIEW_REQUIRED")

        async with async_session_factory() as session:
            regions = (
                await session.execute(
                    select(document_regions).where(
                        document_regions.c.document_version_id == seeded["version_id"]
                    )
                )
            ).mappings().all()
            nodes = (
                await session.execute(
                    select(document_nodes).where(
                        document_nodes.c.document_version_id == seeded["version_id"]
                    )
                )
            ).mappings().all()

        assert len(regions) > 0
        assert len(nodes) > 0
        assert all(row["organization_id"] == seeded["org_id"] for row in nodes)
        assert all(row["organization_id"] == seeded["org_id"] for row in regions)
    finally:
        await _cleanup_parsing_rows(seeded["version_id"])


def _oversized_pipeline_result() -> PipelineResult:
    region = RegionRecord(
        region_type="FREEFORM_SECTION", page_start=1, page_end=1, sequence_number=0,
        confidence=0.9,
    )
    node = NodeSpec(
        id=uuid.uuid4(),
        region_id=region.id,
        parent_id=None,
        node_type="TITLE",
        label="title",
        # Exceeds document_nodes.title's String(1024) column — forces a real
        # StringDataRightTruncation from Postgres during the bulk insert.
        title="x" * 2000,
        number_raw=None,
        number_normalized=None,
        numbering_style=None,
        text="x" * 2000,
        normalized_text="x" * 2000,
        depth=0,
        sequence_number=0,
        page_start=1,
        page_end=1,
        bounding_box=None,
        confidence=0.9,
        source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
        has_direct_page=True,
    )
    return PipelineResult(
        regions=[region], nodes=[node], final_level=ParserLevel.LEVEL_1_NATIVE, status="PARSED"
    )


@pytest.mark.asyncio
async def test_parse_document_marks_job_failed_when_persistence_fails(seeded_document_version):
    # A DB-level failure while persisting regions/nodes (e.g. a column-length
    # violation from an extracted title) must never leave the job stuck at
    # PROCESSING forever with no error — it must resolve to FAILED so the
    # frontend poller in document-list.tsx actually stops polling.
    seeded = seeded_document_version
    content = digital_text_pdf()
    storage_path = (
        f"organization/{seeded['org_id']}/documents/{seeded['document_id']}/"
        f"versions/{seeded['version_id']}/original/test.pdf"
    )
    _put_test_object(storage_path, content)
    await _seed_version_and_job(seeded, storage_path, content)

    try:
        with patch("app.tasks.run_pipeline", return_value=_oversized_pipeline_result()):
            await _parse_document_async(str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "FAILED"
        assert job["error_message"] is not None

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "PROCESSING_FAILED"
    finally:
        await _cleanup_parsing_rows(seeded["version_id"])
