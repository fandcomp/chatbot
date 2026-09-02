"""Cross-organization access must be impossible for knowledge spaces,
documents, and processing jobs. Mandatory per ADR-009/§97.

Requires `docker compose up -d` to be running from the repo root.
"""

import pytest

from app.ingestion import router as ingestion_router

ORG_A_PAYLOAD = {
    "organization_name": "Org A",
    "email": "owner@org-a.io",
    "password": "supersecret123",
}
ORG_B_PAYLOAD = {
    "organization_name": "Org B",
    "email": "owner@org-b.io",
    "password": "supersecret123",
}

_PDF_BYTES = b"%PDF-1.4\n%test document content\n%%EOF"


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ingestion_router, "enqueue_verify_upload", lambda job_id: "fake-celery-task-id"
    )


async def test_org_a_cannot_see_org_bs_knowledge_space(client_factory) -> None:
    # Arrange
    client_a, client_b = client_factory(), client_factory()
    await client_a.post("/auth/register", json=ORG_A_PAYLOAD)
    await client_b.post("/auth/register", json=ORG_B_PAYLOAD)
    org_b_space_id = (await client_b.get("/knowledge-spaces")).json()[0]["id"]

    # Act
    response = await client_a.get(f"/knowledge-spaces/{org_b_space_id}")

    # Assert
    assert response.status_code == 404


async def test_org_a_cannot_see_org_bs_document_or_job(client_factory) -> None:
    # Arrange
    client_a, client_b = client_factory(), client_factory()
    await client_a.post("/auth/register", json=ORG_A_PAYLOAD)
    await client_b.post("/auth/register", json=ORG_B_PAYLOAD)
    org_b_space_id = (await client_b.get("/knowledge-spaces")).json()[0]["id"]
    upload_response = await client_b.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": org_b_space_id},
    )
    org_b_document_id = upload_response.json()["document_id"]
    org_b_job_id = upload_response.json()["processing_job_id"]

    # Act
    document_response = await client_a.get(f"/documents/{org_b_document_id}")
    job_response = await client_a.get(f"/processing-jobs/{org_b_job_id}")
    list_response = await client_a.get("/documents")

    # Assert
    assert document_response.status_code == 404
    assert job_response.status_code == 404
    assert list_response.json() == []


async def test_org_a_cannot_delete_org_bs_document(client_factory) -> None:
    # Arrange
    client_a, client_b = client_factory(), client_factory()
    await client_a.post("/auth/register", json=ORG_A_PAYLOAD)
    await client_b.post("/auth/register", json=ORG_B_PAYLOAD)
    org_b_space_id = (await client_b.get("/knowledge-spaces")).json()[0]["id"]
    upload_response = await client_b.post(
        "/documents/upload",
        files={"file": ("report.pdf", _PDF_BYTES, "application/pdf")},
        data={"knowledge_space_id": org_b_space_id},
    )
    org_b_document_id = upload_response.json()["document_id"]

    # Act
    response = await client_a.delete(f"/documents/{org_b_document_id}")

    # Assert
    assert response.status_code == 404
