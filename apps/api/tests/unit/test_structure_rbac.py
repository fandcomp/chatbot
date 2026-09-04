"""RBAC and correctness checks for M4's structure-review endpoints (addendum
§27): VIEWER can read the structure tree but never correct/approve it;
EDITOR can do both. Also verifies the node-correction endpoint never mutates
a node's original extracted text (addendum §27's core guarantee).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.documents.models import DocumentVersion
from app.ingestion import router as ingestion_router
from app.ingestion.models import ProcessingJob
from app.parsing import router as parsing_router
from app.parsing.models import DocumentNode, DocumentNodeType, DocumentRegion, StructuralRegionType

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
    monkeypatch.setattr(
        parsing_router, "enqueue_chunk_document", lambda job_id: "fake-celery-task-id"
    )


async def _create_member(owner_client: AsyncClient, email: str, role: str) -> None:
    await owner_client.post(
        "/organizations/members",
        json={"email": email, "password": "supersecret123", "role": role},
    )


async def _upload_and_seed_structure(
    owner_client: AsyncClient, version_status: str = "REVIEW_REQUIRED"
) -> tuple[str, uuid.UUID]:
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    upload_response = await owner_client.post(
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
        await session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(status=version_status)
        )

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
            text="Original extracted text — must never change.",
            source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
            structural_path_json=[{"node_type": "PARAGRAPH", "label": None, "title": None}],
            structural_depth=1,
        )
        session.add(node)
        await session.commit()

    return document_id, node.id


async def _upload_and_seed_parent_child(owner_client: AsyncClient) -> tuple[str, uuid.UUID, uuid.UUID]:
    space_id = (await owner_client.get("/knowledge-spaces")).json()[0]["id"]
    upload_response = await owner_client.post(
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
        await session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(status="REVIEW_REQUIRED")
        )

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

        parent_node = DocumentNode(
            organization_id=organization_id,
            document_version_id=version_id,
            region_id=region.id,
            node_type=DocumentNodeType.SECTION,
            depth=0,
            sequence_number=0,
            page_start=1,
            page_end=1,
            confidence=0.9,
            text="Parent paragraph.",
            source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
            structural_path_json=[{"node_type": "SECTION", "label": None, "title": None}],
            structural_depth=1,
        )
        session.add(parent_node)
        await session.flush()

        child_node = DocumentNode(
            organization_id=organization_id,
            document_version_id=version_id,
            region_id=region.id,
            parent_id=parent_node.id,
            node_type=DocumentNodeType.PARAGRAPH,
            depth=1,
            sequence_number=0,
            page_start=1,
            page_end=1,
            confidence=0.9,
            text="Child paragraph.",
            source_provenance={"parser": "docling", "level": "LEVEL_1_NATIVE", "page": 1},
            structural_path_json=[
                {"node_type": "SECTION", "label": None, "title": None},
                {"node_type": "PARAGRAPH", "label": None, "title": None},
            ],
            structural_depth=2,
        )
        session.add(child_node)
        await session.commit()

    return document_id, parent_node.id, child_node.id


async def test_patch_rejects_a_node_becoming_its_own_parent(client_factory) -> None:
    owner_client = client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    document_id, parent_id, _child_id = await _upload_and_seed_parent_child(owner_client)

    response = await owner_client.patch(
        f"/documents/{document_id}/nodes/{parent_id}", json={"parent_id": str(parent_id)}
    )

    assert response.status_code == 400


async def test_patch_rejects_moving_a_node_under_its_own_descendant(client_factory) -> None:
    owner_client = client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    document_id, parent_id, child_id = await _upload_and_seed_parent_child(owner_client)

    response = await owner_client.patch(
        f"/documents/{document_id}/nodes/{parent_id}", json={"parent_id": str(child_id)}
    )

    assert response.status_code == 400


async def test_viewer_can_read_structure(client_factory) -> None:
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer@acme-regulatory.io", "VIEWER")
    document_id, _node_id = await _upload_and_seed_structure(owner_client)
    await viewer_client.post(
        "/auth/login", json={"email": "viewer@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await viewer_client.get(f"/documents/{document_id}/structure")

    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 1


async def test_viewer_cannot_correct_a_node(client_factory) -> None:
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer2@acme-regulatory.io", "VIEWER")
    document_id, node_id = await _upload_and_seed_structure(owner_client)
    await viewer_client.post(
        "/auth/login", json={"email": "viewer2@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await viewer_client.patch(
        f"/documents/{document_id}/nodes/{node_id}", json={"node_type": "ARTICLE"}
    )

    assert response.status_code == 403


async def test_viewer_cannot_approve_a_document(client_factory) -> None:
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer3@acme-regulatory.io", "VIEWER")
    document_id, _node_id = await _upload_and_seed_structure(owner_client)
    await viewer_client.post(
        "/auth/login", json={"email": "viewer3@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await viewer_client.post(f"/documents/{document_id}/approve")

    assert response.status_code == 403


async def test_editor_can_correct_a_node_without_mutating_its_text(client_factory) -> None:
    owner_client, editor_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "editor@acme-regulatory.io", "EDITOR")
    document_id, node_id = await _upload_and_seed_structure(owner_client)
    await editor_client.post(
        "/auth/login", json={"email": "editor@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await editor_client.patch(
        f"/documents/{document_id}/nodes/{node_id}",
        json={
            "node_type": "ARTICLE",
            "label": "Pasal 1",
            "text": "an attacker-supplied rewrite of the extracted text",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["node_type"] == "ARTICLE"
    assert body["label"] == "Pasal 1"
    assert body["text"] == "Original extracted text — must never change."
    assert body["structural_path_text"] == "Pasal 1"


async def test_editor_can_approve_a_document_pending_review(client_factory) -> None:
    owner_client, editor_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "editor2@acme-regulatory.io", "EDITOR")
    document_id, _node_id = await _upload_and_seed_structure(
        owner_client, version_status="REVIEW_REQUIRED"
    )
    await editor_client.post(
        "/auth/login", json={"email": "editor2@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await editor_client.post(f"/documents/{document_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


async def test_approve_creates_a_new_processing_job_and_enqueues_chunking(
    client_factory,
) -> None:
    owner_client = client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    document_id, _node_id = await _upload_and_seed_structure(
        owner_client, version_status="REVIEW_REQUIRED"
    )
    document_before = (await owner_client.get(f"/documents/{document_id}")).json()
    version_id = uuid.UUID(document_before["latest_version_id"])
    original_job_id = uuid.UUID(document_before["latest_processing_job_id"])

    response = await owner_client.post(f"/documents/{document_id}/approve")
    assert response.status_code == 200

    async with async_session_factory() as session:
        jobs = (
            await session.execute(
                select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
            )
        ).scalars().all()

    # The original M2-M4 job plus a brand-new chunking job — never the same
    # row regressed back to an active status.
    assert len(jobs) == 2
    new_job = next(job for job in jobs if job.id != original_job_id)
    assert new_job.status.value == "QUEUED"
    assert new_job.celery_task_id == "fake-celery-task-id"


async def test_approve_rejects_a_document_not_pending_review(client_factory) -> None:
    owner_client, editor_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "editor3@acme-regulatory.io", "EDITOR")
    document_id, _node_id = await _upload_and_seed_structure(
        owner_client, version_status="PARSED"
    )
    await editor_client.post(
        "/auth/login", json={"email": "editor3@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await editor_client.post(f"/documents/{document_id}/approve")

    assert response.status_code == 409
