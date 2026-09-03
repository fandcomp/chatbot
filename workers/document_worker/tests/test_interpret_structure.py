import uuid

import pytest
from sqlalchemy import insert, select, text

from app.core.config import settings
from app.database import (
    async_session_factory,
    document_nodes,
    document_regions,
    document_structure_profiles,
    document_versions,
    processing_jobs,
)
from app.tasks import _interpret_structure_async


async def _seed_version_and_job(seeded: dict, status: str = "PARSED") -> None:
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
                status="PROCESSING",
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
        node_type="PARAGRAPH",
        label=None,
        title=None,
        number_raw=None,
        number_normalized=None,
        numbering_style=None,
        text=None,
        normalized_text=None,
        depth=0,
        sequence_number=0,
        page_start=1,
        page_end=1,
        bounding_box=None,
        confidence=0.9,
        source_provenance={},
        structural_path_json=[],
        structural_depth=0,
    )
    defaults.update(overrides)
    return defaults


async def _seed_nodes(rows: list[dict]) -> None:
    async with async_session_factory() as session:
        await session.execute(insert(document_nodes), rows)
        await session.commit()


async def _cleanup(version_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("DELETE FROM document_structure_profiles WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        await session.execute(
            text("DELETE FROM document_nodes WHERE document_version_id = :vid"), {"vid": version_id}
        )
        await session.execute(
            text("DELETE FROM document_regions WHERE document_version_id = :vid"),
            {"vid": version_id},
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


async def _node_rows(version_id) -> list[dict]:
    async with async_session_factory() as session:
        return [
            dict(row)
            for row in (
                await session.execute(
                    select(document_nodes).where(
                        document_nodes.c.document_version_id == version_id
                    )
                )
            )
            .mappings()
            .all()
        ]


@pytest.mark.asyncio
async def test_interpret_structure_retypes_nodes_and_marks_version_approved(
    seeded_document_version,
):
    seeded = seeded_document_version
    await _seed_version_and_job(seeded, status="PARSED")
    region_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_nodes(
        [
            _node_values(
                seeded,
                region_id,
                node_type="PARAGRAPH",
                text="Pasal 1",
                depth=0,
                sequence_number=0,
            ),
            _node_values(
                seeded,
                region_id,
                node_type="LIST_ITEM",
                text="(1) Definisi umum.",
                numbering_style="DECIMAL_PAREN_FULL",
                number_normalized="1",
                depth=1,
                sequence_number=0,
            ),
        ]
    )

    try:
        await _interpret_structure_async(str(seeded["job_id"]), attempts=1)

        job = await _job_row(seeded["job_id"])
        assert job["status"] == "SUCCEEDED"

        version = await _version_row(seeded["version_id"])
        assert version["status"] in ("APPROVED", "REVIEW_REQUIRED")

        nodes = await _node_rows(seeded["version_id"])
        node_types = {node["node_type"] for node in nodes}
        assert "ARTICLE" in node_types
        assert "CLAUSE" in node_types
        assert all(node["structural_path_text"] for node in nodes)

        async with async_session_factory() as session:
            profile = (
                await session.execute(
                    select(document_structure_profiles).where(
                        document_structure_profiles.c.document_version_id
                        == seeded["version_id"]
                    )
                )
            ).mappings().one()
        assert profile["contains_articles"] is True
    finally:
        await _cleanup(seeded["version_id"])


@pytest.mark.asyncio
async def test_interpret_structure_never_upgrades_an_ocr_driven_review_required(
    seeded_document_version,
):
    # M3 may have already set REVIEW_REQUIRED for OCR-fallback reasons — the
    # extracted text itself is suspect, independent of how confidently M4
    # re-types it, so M4 must never silently upgrade that to APPROVED.
    seeded = seeded_document_version
    await _seed_version_and_job(seeded, status="REVIEW_REQUIRED")
    region_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    await _seed_nodes(
        [
            _node_values(
                seeded, region_id, node_type="PARAGRAPH", text="Pasal 1", confidence=0.99
            ),
        ]
    )

    try:
        await _interpret_structure_async(str(seeded["job_id"]), attempts=1)

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "REVIEW_REQUIRED"
    finally:
        await _cleanup(seeded["version_id"])


@pytest.mark.asyncio
async def test_interpret_structure_marks_review_required_when_confidence_is_low(
    seeded_document_version,
):
    seeded = seeded_document_version
    await _seed_version_and_job(seeded, status="PARSED")
    region_id = uuid.uuid4()
    await _seed_region(seeded, region_id)
    low_confidence = settings.STRUCTURE_REVIEW_THRESHOLD
    await _seed_nodes(
        [
            _node_values(
                seeded,
                region_id,
                node_type="PARAGRAPH",
                text="Pasal 1",
                confidence=low_confidence,
            ),
        ]
    )

    try:
        await _interpret_structure_async(str(seeded["job_id"]), attempts=1)

        version = await _version_row(seeded["version_id"])
        assert version["status"] == "REVIEW_REQUIRED"
    finally:
        await _cleanup(seeded["version_id"])
