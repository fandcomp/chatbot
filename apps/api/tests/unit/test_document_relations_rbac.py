"""RBAC and correctness checks for the document-relations endpoints (spec
§21) against real Postgres — same pattern as test_document_rbac.py.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.database import async_session_factory
from app.documents.models import DocumentLifecycleStatus, DocumentVersion
from app.ingestion import router as ingestion_router

REGISTER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
}
OTHER_ORG_PAYLOAD = {
    "organization_name": "Other Org",
    "email": "owner@other-org.io",
    "password": "supersecret123",
}

def _pdf_bytes(filename: str) -> bytes:
    # Content must differ per upload — uq_document_version_org_hash rejects a
    # second upload in the same org whose file_hash (content SHA-256)
    # matches an existing version, and every test here uploads two documents.
    return f"%PDF-1.4\n%test document content {filename}\n%%EOF".encode()


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def _create_member(owner_client: AsyncClient, email: str, role: str) -> None:
    await owner_client.post(
        "/organizations/members",
        json={"email": email, "password": "supersecret123", "role": role},
    )


async def _upload(client: AsyncClient, space_id: str, filename: str = "report.pdf") -> str:
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, _pdf_bytes(filename), "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    return response.json()["document_id"]


async def _upload_and_activate(client: AsyncClient, space_id: str, filename: str) -> str:
    """A relation's "from" side must have cleared approval (see
    latest_active_version in documents/router.py) — `enqueue_verify_upload`
    is stubbed out in this file, so no upload here ever reaches ACTIVE on its
    own. This mirrors test_structure_rbac.py's direct-DB-update pattern to
    fast-forward a freshly uploaded version straight to ACTIVE.
    """
    response = await client.post(
        "/documents/upload",
        files={"file": (filename, _pdf_bytes(filename), "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    body = response.json()
    async with async_session_factory() as session:
        await session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == uuid.UUID(body["document_version_id"]))
            .values(status=DocumentLifecycleStatus.ACTIVE)
        )
        await session.commit()
    return body["document_id"]


async def test_editor_can_create_a_relation_between_two_of_the_orgs_documents(
    client_factory,
) -> None:
    # Arrange
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload_and_activate(owner, space_id, "b.pdf")

    # Act
    response = await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "AMENDS"},
    )

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["from_document_id"] == doc_b
    assert body["to_document_id"] == doc_a
    assert body["relation_type"] == "AMENDS"


async def test_viewer_cannot_create_a_relation(client_factory) -> None:
    # Arrange
    owner, viewer = client_factory(), client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner, "viewer@acme-regulatory.io", "VIEWER")
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload(owner, space_id, "b.pdf")
    await viewer.post(
        "/auth/login", json={"email": "viewer@acme-regulatory.io", "password": "supersecret123"}
    )

    # Act
    response = await viewer.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "AMENDS"},
    )

    # Assert
    assert response.status_code == 403


async def test_cannot_relate_a_document_to_itself(client_factory) -> None:
    # Arrange
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")

    # Act
    response = await owner.post(
        f"/documents/{doc_a}/relations",
        json={"target_document_id": doc_a, "relation_type": "AMENDS"},
    )

    # Assert
    assert response.status_code == 400


async def test_cannot_create_superseded_by_via_the_api(client_factory) -> None:
    # Arrange
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload(owner, space_id, "b.pdf")

    # Act
    response = await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "SUPERSEDED_BY"},
    )

    # Assert
    assert response.status_code == 400


async def test_cannot_create_a_relation_from_a_document_that_is_not_yet_active(
    client_factory,
) -> None:
    # A freshly uploaded document (never approved/published) must not be
    # usable as the "from" side of a relation — its title/relation type
    # would otherwise reach another (already-ACTIVE) document's citations
    # before this one has ever passed admin review.
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload_and_activate(owner, space_id, "a.pdf")
    doc_b = await _upload(owner, space_id, "b.pdf")  # still UPLOADED, never approved

    # Act
    response = await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "AMENDS"},
    )

    # Assert
    assert response.status_code == 400


async def test_cannot_relate_to_another_organizations_document(client_factory) -> None:
    # Arrange
    owner_a, owner_b = client_factory(), client_factory()
    await owner_a.post("/auth/register", json=REGISTER_PAYLOAD)
    await owner_b.post("/auth/register", json=OTHER_ORG_PAYLOAD)
    space_a = (await owner_a.get("/knowledge-spaces")).json()[0]["id"]
    space_b = (await owner_b.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner_a, space_a, "a.pdf")
    doc_b = await _upload(owner_b, space_b, "b.pdf")

    # Act
    response = await owner_a.post(
        f"/documents/{doc_a}/relations",
        json={"target_document_id": doc_b, "relation_type": "AMENDS"},
    )

    # Assert
    assert response.status_code == 404


async def test_list_relations_shows_a_relation_from_either_side(client_factory) -> None:
    # Arrange
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload_and_activate(owner, space_id, "b.pdf")
    await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "REPEALS"},
    )

    # Act
    from_a = await owner.get(f"/documents/{doc_a}/relations")
    from_b = await owner.get(f"/documents/{doc_b}/relations")

    # Assert
    assert len(from_a.json()) == 1
    assert len(from_b.json()) == 1
    assert from_a.json()[0]["relation_type"] == "REPEALS"


async def test_delete_relation_removes_it(client_factory) -> None:
    # Arrange
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload_and_activate(owner, space_id, "b.pdf")
    create_response = await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "REPLACES"},
    )
    relation_id = create_response.json()["id"]

    # Act
    delete_response = await owner.delete(f"/documents/relations/{relation_id}")
    list_response = await owner.get(f"/documents/{doc_a}/relations")

    # Assert
    assert delete_response.status_code == 204
    assert list_response.json() == []


async def test_deleting_a_document_with_a_relation_does_not_fail(client_factory) -> None:
    # A document that has ever been the "to" side of a relation (manual, or
    # M13's own auto-created SUPERSEDED_BY) must still be deletable — the
    # relation row has no ON DELETE CASCADE, so this is a real
    # ForeignKeyViolationError risk without the router's own cleanup.
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]
    doc_a = await _upload(owner, space_id, "a.pdf")
    doc_b = await _upload_and_activate(owner, space_id, "b.pdf")
    await owner.post(
        f"/documents/{doc_b}/relations",
        json={"target_document_id": doc_a, "relation_type": "AMENDS"},
    )

    # Act
    response = await owner.delete(f"/documents/{doc_a}")

    # Assert
    assert response.status_code == 204
