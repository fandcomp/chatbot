"""Integration tests for the reprocess action (POST
/documents/{document_id}/versions/{version_id}/reprocess) — manually
re-triggering a PROCESSING_FAILED version's pipeline from scratch.

Requires `docker compose up -d` to be running from the repo root.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.chunking.models import DocumentChunk
from app.core.database import async_session_factory
from app.documents import router as documents_router
from app.documents.models import DocumentLifecycleStatus
from app.ingestion.models import ProcessingJob, ProcessingJobStatus
from app.parsing.models import (
    DocumentNode,
    DocumentNodeType,
    DocumentRegion,
    DocumentStructureProfile,
)

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Reprocess Test Org",
    "email": "owner@reprocess-test.io",
    "password": "supersecret123",
}


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        documents_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def _seed_failed_version_with_partial_state(client: AsyncClient) -> tuple[str, uuid.UUID]:
    """A version that reached PROCESSING_FAILED AFTER parse_document and
    chunk_document had already committed their own rows for it — the exact
    case that would duplicate data if reprocess just re-ran the pipeline
    without first clearing what earlier stages already wrote.
    """
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(
            db, org_id, ks_id, status=DocumentLifecycleStatus.PROCESSING_FAILED
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 1\nKetentuan umum.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 1", "title": None}],
            structural_path_text="Pasal 1",
            article_number="1",
        )
        db.add(
            DocumentStructureProfile(
                organization_id=org_id,
                document_version_id=version_id,
                contains_articles=True,
                contains_numbered_sections=False,
                contains_chapters=False,
                contains_decision_preamble=False,
                contains_appendices=False,
                contains_tables=False,
                contains_diagrams=False,
                contains_embedded_document=False,
            )
        )
        await db.commit()

    return document_id, version_id


async def test_reprocessing_a_failed_version_clears_partial_state_and_queues_a_new_job(
    client: AsyncClient,
) -> None:
    # Arrange
    document_id, version_id = await _seed_failed_version_with_partial_state(client)

    # Act
    response = await client.post(f"/documents/{document_id}/versions/{version_id}/reprocess")

    # Assert — restarted from scratch, exactly like a fresh upload.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UPLOADED"
    new_job_id = uuid.UUID(body["processing_job_id"])

    async with async_session_factory() as db:
        remaining_chunks = (
            await db.execute(
                select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
            )
        ).scalars().all()
        assert remaining_chunks == []

        remaining_nodes = (
            await db.execute(
                select(DocumentNode).where(DocumentNode.document_version_id == version_id)
            )
        ).scalars().all()
        assert remaining_nodes == []

        remaining_regions = (
            await db.execute(
                select(DocumentRegion).where(DocumentRegion.document_version_id == version_id)
            )
        ).scalars().all()
        assert remaining_regions == []

        remaining_profiles = (
            await db.execute(
                select(DocumentStructureProfile).where(
                    DocumentStructureProfile.document_version_id == version_id
                )
            )
        ).scalars().all()
        assert remaining_profiles == []

        new_job = (
            await db.execute(select(ProcessingJob).where(ProcessingJob.id == new_job_id))
        ).scalar_one()
        assert new_job.status == ProcessingJobStatus.QUEUED
        assert new_job.celery_task_id == "fake-celery-task-id"


async def test_cannot_reprocess_a_version_that_has_not_failed(client: AsyncClient) -> None:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, _region_id = await seed_active_document(
            db, org_id, ks_id, status=DocumentLifecycleStatus.ACTIVE
        )
        await db.commit()

    response = await client.post(f"/documents/{document_id}/versions/{version_id}/reprocess")
    assert response.status_code == 409
