"""Integration tests for the upload -> job -> document flow against real
Postgres + MinIO.

`enqueue_verify_upload` is monkeypatched so these tests don't depend on a live
Celery worker consuming the queue (that's a separate long-running process,
covered instead by workers/document_worker's own tests calling the task
function directly). These tests only assert the QUEUED job/row state is
created correctly.

Requires `docker compose up -d` to be running from the repo root.
"""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.chunking.models import DocumentChunk
from app.core.database import async_session_factory
from app.documents import router as documents_router
from app.documents.models import DocumentVersion
from app.ingestion import router as ingestion_router
from app.parsing.models import (
    DocumentNode,
    DocumentNodeType,
    DocumentRegion,
    StructuralRegionType,
)

REGISTER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
    "full_name": "Ada Owner",
}

_PDF_BYTES = b"%PDF-1.4\n%test document content\n%%EOF"


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def _register_and_get_space_id(client: AsyncClient) -> str:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    spaces = await client.get("/knowledge-spaces")
    return spaces.json()[0]["id"]


async def test_register_auto_creates_general_knowledge_space(client: AsyncClient) -> None:
    # Act
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    response = await client.get("/knowledge-spaces")

    # Assert
    assert response.status_code == 200
    spaces = response.json()
    assert len(spaces) == 1
    assert spaces[0]["name"] == "General"


async def test_upload_creates_document_version_and_queued_job(client: AsyncClient) -> None:
    # Arrange
    space_id = await _register_and_get_space_id(client)

    # Act
    response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "UPLOADED"

    job_response = await client.get(f"/processing-jobs/{body['processing_job_id']}")
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "QUEUED"

    documents_response = await client.get("/documents")
    documents = documents_response.json()
    assert len(documents) == 1
    assert documents[0]["title"] == "report"
    assert documents[0]["latest_version_status"] == "UPLOADED"


async def test_duplicate_upload_returns_409(client: AsyncClient) -> None:
    # Arrange
    space_id = await _register_and_get_space_id(client)
    await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Act
    response = await client.post(
        "/documents/upload",
        files={"file": ("report-copy.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 409


async def test_upload_with_wrong_extension_is_rejected(client: AsyncClient) -> None:
    # Arrange
    space_id = await _register_and_get_space_id(client)

    # Act
    response = await client.post(
        "/documents/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 422


async def test_upload_exceeding_max_size_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setattr(ingestion_router.settings, "MAX_FILE_SIZE_MB", 0)
    space_id = await _register_and_get_space_id(client)

    # Act
    response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 422


async def test_delete_document_removes_it_and_its_processing_job(client: AsyncClient) -> None:
    # Arrange — a real ProcessingJob row exists (created by upload) referencing
    # the DocumentVersion being deleted; this must not violate FK constraints.
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    job_id = upload_response.json()["processing_job_id"]

    # Act
    delete_response = await client.delete(f"/documents/{document_id}")

    # Assert
    assert delete_response.status_code == 204
    assert (await client.get(f"/documents/{document_id}")).status_code == 404
    assert (await client.get(f"/processing-jobs/{job_id}")).status_code == 404
    assert (await client.get("/documents")).json() == []


async def test_delete_document_removes_a_parsed_documents_regions_and_nodes(
    client: AsyncClient,
) -> None:
    # Arrange — simulate M3's worker having already populated document_regions/
    # document_nodes for this version (the worker runs out-of-process, so this
    # suite can't exercise it directly). Deleting a document that reached
    # PARSED/REVIEW_REQUIRED must not hit a ForeignKeyViolationError.
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    version_id = uuid.UUID(upload_response.json()["document_version_id"])

    async with async_session_factory() as session:
        # organization_id isn't exposed on DocumentPublic; pull it off the version.
        version = (
            await session.execute(
                select(DocumentVersion).where(DocumentVersion.id == version_id)
            )
        ).scalar_one()
        organization_id = version.organization_id

        region = DocumentRegion(
            organization_id=organization_id,
            document_version_id=version_id,
            region_type=StructuralRegionType.FREEFORM_SECTION,
            page_start=1,
            page_end=1,
            sequence_number=0,
            confidence=0.9,
        )
        session.add(region)
        await session.flush()

        node = DocumentNode(
            organization_id=organization_id,
            document_version_id=version_id,
            region_id=region.id,
            node_type=DocumentNodeType.PARAGRAPH,
            depth=0,
            sequence_number=0,
            page_start=1,
            page_end=1,
            confidence=0.9,
            source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
            structural_path_json=[{"node_type": "PARAGRAPH", "label": None, "title": None}],
            structural_depth=1,
        )
        session.add(node)
        await session.commit()

    # Act
    delete_response = await client.delete(f"/documents/{document_id}")

    # Assert
    assert delete_response.status_code == 204
    async with async_session_factory() as session:
        remaining_nodes = (
            await session.execute(
                select(DocumentNode).where(DocumentNode.document_version_id == version_id)
            )
        ).scalars().all()
        remaining_regions = (
            await session.execute(
                select(DocumentRegion).where(DocumentRegion.document_version_id == version_id)
            )
        ).scalars().all()
        assert remaining_nodes == []
        assert remaining_regions == []


async def test_delete_document_removes_chunks_and_cleans_up_qdrant(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — simulate M5/M6 having populated document_chunks (referencing
    # a node via a NOT NULL, non-cascading FK) for a version that reached
    # ACTIVE. Deleting it must not hit a ForeignKeyViolationError, and must
    # call M6's Qdrant cleanup (ADR-002: stale points are disallowed).
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    version_id = uuid.UUID(upload_response.json()["document_version_id"])

    async with async_session_factory() as session:
        version = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == version_id))
        ).scalar_one()
        organization_id = version.organization_id

        region = DocumentRegion(
            organization_id=organization_id,
            document_version_id=version_id,
            region_type=StructuralRegionType.FREEFORM_SECTION,
            page_start=1,
            page_end=1,
            sequence_number=0,
            confidence=0.9,
        )
        session.add(region)
        await session.flush()

        node = DocumentNode(
            organization_id=organization_id,
            document_version_id=version_id,
            region_id=region.id,
            node_type=DocumentNodeType.PARAGRAPH,
            depth=0,
            sequence_number=0,
            page_start=1,
            page_end=1,
            confidence=0.9,
            source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
            structural_path_json=[{"node_type": "PARAGRAPH", "label": None, "title": None}],
            structural_depth=1,
        )
        session.add(node)
        await session.flush()

        chunk = DocumentChunk(
            organization_id=organization_id,
            document_id=uuid.UUID(document_id),
            document_version_id=version_id,
            source_node_id=node.id,
            depth=0,
            sequence_number=0,
            page_start=1,
            page_end=1,
            original_text="Original text.",
            contextual_text="Dokumen: report\nOriginal text.",
            token_count=5,
            structural_path_text=None,
        )
        session.add(chunk)
        await session.commit()

    mock_delete_points = AsyncMock()
    monkeypatch.setattr(documents_router, "delete_document_points", mock_delete_points)

    # Act
    delete_response = await client.delete(f"/documents/{document_id}")

    # Assert
    assert delete_response.status_code == 204
    mock_delete_points.assert_called_once_with(organization_id, uuid.UUID(document_id))
    async with async_session_factory() as session:
        remaining_chunks = (
            await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
            )
        ).scalars().all()
        assert remaining_chunks == []


async def test_delete_document_rolls_back_when_qdrant_cleanup_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A Qdrant delete failure must abort the whole transaction before
    # anything commits — the document (and everything under it) must survive,
    # mirroring the existing S3 delete_object placement's failure semantics.
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]

    monkeypatch.setattr(
        documents_router,
        "delete_document_points",
        AsyncMock(side_effect=RuntimeError("Qdrant unreachable")),
    )

    with pytest.raises(RuntimeError, match="Qdrant unreachable"):
        await client.delete(f"/documents/{document_id}")

    async with async_session_factory() as session:
        remaining_version = (
            await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == uuid.UUID(document_id)
                )
            )
        ).scalar_one_or_none()
        assert remaining_version is not None


async def test_upload_with_unknown_knowledge_space_returns_404(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": "00000000-0000-0000-0000-000000000000"},
    )

    # Assert
    assert response.status_code == 404
