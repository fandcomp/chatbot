"""Integration tests for M13's rollback action (`POST
/documents/{document_id}/versions/{version_id}/rollback`) — restoring a
previously-ACTIVE version (SUPERSEDED or ARCHIVED) back to ACTIVE. The
complement of archive_document/the worker's auto-supersede, both of which
only ever move a version forward, out of ACTIVE.

Requires `docker compose up -d` to be running from the repo root.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.redis_client import redis_client
from app.documents.models import (
    Document,
    DocumentLifecycleStatus,
    DocumentRelation,
    DocumentVersion,
)
from app.ingestion import router as ingestion_router

REGISTER_PAYLOAD = {
    "organization_name": "Rollback Test Org",
    "email": "owner@rollback-test.io",
    "password": "supersecret123",
    "full_name": "Ada Owner",
}

_PDF_BYTES_V1 = b"%PDF-1.4\n%rollback test v1\n%%EOF"
_PDF_BYTES_V2 = b"%PDF-1.4\n%rollback test v2, different content\n%%EOF"


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def _register_and_get_space_id(client: AsyncClient) -> str:
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    spaces = await client.get("/knowledge-spaces")
    return spaces.json()[0]["id"]


async def _set_status(version_id: uuid.UUID, status: DocumentLifecycleStatus) -> None:
    async with async_session_factory() as session:
        version = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == version_id))
        ).scalar_one()
        version.status = status
        await session.commit()


async def _two_version_document(client: AsyncClient) -> tuple[str, uuid.UUID, uuid.UUID]:
    """v1 SUPERSEDED, v2 ACTIVE — the shape after a normal forward
    supersede (M13's existing auto-supersede logic). Returns
    (document_id, v1_id, v2_id).
    """
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES_V1, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    v1_id = uuid.UUID(upload_response.json()["document_version_id"])

    version_response = await client.post(
        f"/documents/{document_id}/versions",
        files={"file": ("report-v2.pdf", _PDF_BYTES_V2, "application/pdf")},
    )
    v2_id = uuid.UUID(version_response.json()["document_version_id"])

    await _set_status(v1_id, DocumentLifecycleStatus.SUPERSEDED)
    await _set_status(v2_id, DocumentLifecycleStatus.ACTIVE)

    return document_id, v1_id, v2_id


async def test_rollback_to_superseded_version_reactivates_it_and_supersedes_current(
    client: AsyncClient,
) -> None:
    # Arrange
    document_id, v1_id, v2_id = await _two_version_document(client)

    # Act
    response = await client.post(f"/documents/{document_id}/versions/{v1_id}/rollback")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["document_version_id"] == str(v1_id)
    assert body["status"] == "ACTIVE"
    assert body["superseded_version_id"] == str(v2_id)

    async with async_session_factory() as session:
        v1 = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
        ).scalar_one()
        v2 = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == v2_id))
        ).scalar_one()
    assert v1.status == DocumentLifecycleStatus.ACTIVE
    assert v2.status == DocumentLifecycleStatus.SUPERSEDED


async def test_rollback_records_a_superseded_by_relation_from_old_active_to_target(
    client: AsyncClient,
) -> None:
    # Arrange
    document_id, v1_id, v2_id = await _two_version_document(client)

    # Act
    await client.post(f"/documents/{document_id}/versions/{v1_id}/rollback")

    # Assert — same audit-trail relation type the worker's forward
    # auto-supersede creates, just pointed the other way: v2 (now superseded)
    # -> v1 (now active).
    async with async_session_factory() as session:
        relation = (
            await session.execute(
                select(DocumentRelation).where(
                    DocumentRelation.from_document_version_id == v2_id,
                    DocumentRelation.to_document_version_id == v1_id,
                )
            )
        ).scalar_one()
    assert relation.relation_type.value == "SUPERSEDED_BY"


async def test_rollback_to_archived_version_with_no_current_active(client: AsyncClient) -> None:
    # Arrange — a document with a single version, ARCHIVED, and nothing else
    # currently ACTIVE to supersede.
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES_V1, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    version_id = uuid.UUID(upload_response.json()["document_version_id"])
    await _set_status(version_id, DocumentLifecycleStatus.ARCHIVED)

    # Act
    response = await client.post(f"/documents/{document_id}/versions/{version_id}/rollback")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["superseded_version_id"] is None


async def test_rollback_a_version_that_was_never_active_returns_409(client: AsyncClient) -> None:
    # Arrange — freshly uploaded, still UPLOADED, never reached ACTIVE.
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES_V1, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    version_id = upload_response.json()["document_version_id"]

    # Act
    response = await client.post(f"/documents/{document_id}/versions/{version_id}/rollback")

    # Assert
    assert response.status_code == 409


async def test_rollback_an_already_active_version_returns_409(client: AsyncClient) -> None:
    # Arrange
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES_V1, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    version_id = uuid.UUID(upload_response.json()["document_version_id"])
    await _set_status(version_id, DocumentLifecycleStatus.ACTIVE)

    # Act
    response = await client.post(f"/documents/{document_id}/versions/{version_id}/rollback")

    # Assert
    assert response.status_code == 409


async def test_rollback_unknown_version_returns_404(client: AsyncClient) -> None:
    # Arrange
    space_id = await _register_and_get_space_id(client)
    upload_response = await client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES_V1, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]

    # Act
    response = await client.post(
        f"/documents/{document_id}/versions/00000000-0000-0000-0000-000000000000/rollback"
    )

    # Assert
    assert response.status_code == 404


async def test_rollback_unknown_document_returns_404(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.post(
        "/documents/00000000-0000-0000-0000-000000000000/versions/"
        "00000000-0000-0000-0000-000000000000/rollback"
    )

    # Assert
    assert response.status_code == 404


async def test_list_versions_returns_all_versions_newest_first(client: AsyncClient) -> None:
    # Arrange
    document_id, v1_id, v2_id = await _two_version_document(client)

    # Act
    response = await client.get(f"/documents/{document_id}/versions")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert [entry["id"] for entry in body] == [str(v2_id), str(v1_id)]
    assert body[0]["status"] == "ACTIVE"
    assert body[1]["status"] == "SUPERSEDED"


async def test_list_versions_unknown_document_returns_404(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.get(
        "/documents/00000000-0000-0000-0000-000000000000/versions"
    )

    # Assert
    assert response.status_code == 404


async def test_rollback_invalidates_the_answer_cache(client: AsyncClient) -> None:
    # Arrange
    document_id, v1_id, _v2_id = await _two_version_document(client)

    async with async_session_factory() as session:
        document = (
            await session.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
        ).scalar_one()
        org_id = document.organization_id

    cache_key = f"answer_cache:{org_id}:{uuid.uuid4()}:deadbeef"
    await redis_client.set(cache_key, "{}")

    # Act
    try:
        await client.post(f"/documents/{document_id}/versions/{v1_id}/rollback")
        # Assert
        assert await redis_client.get(cache_key) is None
    finally:
        await redis_client.delete(cache_key)
