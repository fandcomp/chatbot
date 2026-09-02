"""RBAC checks for upload/delete against real Postgres (per §52: VIEWER is
chat-and-read only; EDITOR can upload and manage their own org's documents).

Despite living under tests/unit for now (matching this repo's existing split),
this exercises the real DB via the httpx client fixture, same as the
integration suite.
"""

import pytest
from httpx import AsyncClient

from app.ingestion import router as ingestion_router

REGISTER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
}

_PDF_BYTES = b"%PDF-1.4\n%test document content\n%%EOF"


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def _create_member(
    owner_client: AsyncClient, email: str, role: str
) -> None:
    await owner_client.post(
        "/organizations/members",
        json={"email": email, "password": "supersecret123", "role": role},
    )


async def test_viewer_cannot_upload_a_document(client_factory) -> None:
    # Arrange
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer@acme-regulatory.io", "VIEWER")
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    await viewer_client.post(
        "/auth/login", json={"email": "viewer@acme-regulatory.io", "password": "supersecret123"}
    )

    # Act
    response = await viewer_client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 403


async def test_editor_can_upload_a_document(client_factory) -> None:
    # Arrange
    owner_client, editor_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "editor@acme-regulatory.io", "EDITOR")
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    await editor_client.post(
        "/auth/login", json={"email": "editor@acme-regulatory.io", "password": "supersecret123"}
    )

    # Act
    response = await editor_client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )

    # Assert
    assert response.status_code == 201


async def test_viewer_cannot_delete_a_document(client_factory) -> None:
    # Arrange
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer2@acme-regulatory.io", "VIEWER")
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    upload_response = await owner_client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    document_id = upload_response.json()["document_id"]
    await viewer_client.post(
        "/auth/login", json={"email": "viewer2@acme-regulatory.io", "password": "supersecret123"}
    )

    # Act
    response = await viewer_client.delete(f"/documents/{document_id}")

    # Assert
    assert response.status_code == 403


async def test_viewer_can_still_list_and_read_documents(client_factory) -> None:
    # Arrange
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer3@acme-regulatory.io", "VIEWER")
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    await owner_client.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": space_id},
    )
    await viewer_client.post(
        "/auth/login", json={"email": "viewer3@acme-regulatory.io", "password": "supersecret123"}
    )

    # Act
    response = await viewer_client.get("/documents")

    # Assert
    assert response.status_code == 200
    assert len(response.json()) == 1
