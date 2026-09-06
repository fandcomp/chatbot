"""M12 Test Knowledge (spec §61): an admin can preview answer quality for a
specific document that hasn't reached ACTIVE yet, without exposing it to
real chat's org-wide retrieval. HF client mocked throughout.

Requires `docker compose up -d` to be running from the repo root.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import async_session_factory
from app.documents.models import DocumentLifecycleStatus
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Test Knowledge Org",
    "email": "owner@test-knowledge.io",
    "password": "supersecret123",
}


def _completion(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )


async def _register(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, ks_id


async def test_can_test_a_document_still_in_review_before_it_is_active(client_factory) -> None:
    # Arrange — APPROVED, not ACTIVE: the exact scenario §61 targets.
    client, ks_id = await _register(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(
            db, org_id, ks_id, status=DocumentLifecycleStatus.APPROVED
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 7\nKetentuan sedang direview.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 7", "title": None}],
            structural_path_text="Pasal 7",
            article_number="7",
        )
        await db.commit()

    structured_answer = {
        "answer_type": "FACTUAL_LOOKUP",
        "summary": "Ketentuan sedang direview.",
        "sections": [],
        "claims": [{"text": "Ketentuan sedang direview.", "source_ids": ["S1"]}],
        "insufficient_evidence": False,
        "reason_if_insufficient": None,
    }

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(structured_answer)
        )
        response = await client.post(
            "/knowledge/test", json={"document_id": str(document_id), "query": "Pasal 7"}
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_mode"] == "EXACT_STRUCTURAL"
    assert len(body["retrieved_sources"]) == 1
    assert body["answer"] == "Ketentuan sedang direview."
    assert body["detected_intent"] == "FACTUAL_LOOKUP"
    assert "S1" in body["citations"]


async def test_reviewed_document_is_not_yet_visible_to_real_retrieval(client_factory) -> None:
    # Arrange — same APPROVED (not ACTIVE) document as above.
    client, ks_id = await _register(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(
            db, org_id, ks_id, status=DocumentLifecycleStatus.APPROVED
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 9\nKetentuan sedang direview.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 9", "title": None}],
            structural_path_text="Pasal 9",
            article_number="9",
        )
        await db.commit()

    # Act — the real (non-test) retrieval endpoint must NOT find it; the
    # APPROVED-not-ACTIVE document has no exact match, so this falls through
    # to hybrid search, which still calls Voyage for query embedding (M7's
    # own convention).
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert
    assert response.status_code == 200
    assert response.json()["chunks"] == []


async def test_org_b_cannot_test_knowledge_against_org_as_document(client_factory) -> None:
    # Arrange
    _client_a, ks_id_a = await _register(client_factory)
    client_b = client_factory()
    await client_b.post(
        "/auth/register",
        json={
            "organization_name": "Test Knowledge Org B",
            "email": "owner@test-knowledge-b.io",
            "password": "supersecret123",
        },
    )

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id_a)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id_a)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 3\nRahasia organisasi A.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 3", "title": None}],
            structural_path_text="Pasal 3",
            article_number="3",
        )
        await db.commit()

    # Act
    response = await client_b.post(
        "/knowledge/test", json={"document_id": str(document_id), "query": "Pasal 3"}
    )

    # Assert
    assert response.status_code == 404


async def test_test_knowledge_with_no_chunks_reports_insufficient_evidence(client_factory) -> None:
    # Arrange — a document with zero chunks (e.g. still PROCESSING).
    client, ks_id = await _register(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, _version_id, _region_id = await seed_active_document(
            db, org_id, ks_id, status=DocumentLifecycleStatus.PROCESSING
        )
        await db.commit()

    # Act — no chunks exist, so exact match falls through to hybrid search,
    # which still calls Voyage for query embedding (M7's own convention).
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post(
            "/knowledge/test", json={"document_id": str(document_id), "query": "Pasal 1"}
        )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["retrieved_sources"] == []
