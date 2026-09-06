"""M14 analytics endpoints (spec §62-63, §92): GET /analytics/overview,
GET /analytics/knowledge-gaps, POST /messages/{id}/feedback, plus proof that
real chat and Test Knowledge turns actually write QueryLog/KnowledgeGap rows.
HF/Voyage always mocked — no real Groq/HF/Voyage call.

Requires `docker compose up -d` to be running from the repo root.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.analytics.models import KnowledgeGap, QueryLog, QueryLogSource
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
    "organization_name": "Analytics Endpoint Org",
    "email": "owner@analytics-endpoint.io",
    "password": "supersecret123",
}


def _completion(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    )


_STRUCTURED_ANSWER = {
    "answer_type": "FACTUAL_LOOKUP",
    "summary": "Setiap warga negara berhak atas pendidikan dasar.",
    "sections": [],
    "claims": [
        {"text": "Setiap warga negara berhak atas pendidikan dasar.", "source_ids": ["S1"]}
    ],
    "insufficient_evidence": False,
    "reason_if_insufficient": None,
}


async def _register(client_factory, payload: dict = REGISTER_PAYLOAD):
    client = client_factory()
    await client.post("/auth/register", json=payload)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, ks_id


async def _create_member(owner_client, email: str, role: str) -> None:
    await owner_client.post(
        "/organizations/members",
        json={"email": email, "password": "supersecret123", "role": role},
    )


async def _seed_article(ks_id: str):
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 5\nSetiap warga negara berhak atas pendidikan dasar.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 5", "title": None}],
            structural_path_text="Pasal 5",
            article_number="5",
        )
        await db.commit()
    return document_id


async def test_chat_turn_writes_a_query_log_row(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
    conversation_id = response.json()["conversation_id"]

    # Assert
    async with async_session_factory() as db:
        logs = (
            await db.execute(
                QueryLog.__table__.select().where(
                    QueryLog.conversation_id == conversation_id
                )
            )
        ).mappings().all()
    assert len(logs) == 1
    assert logs[0]["source"] == QueryLogSource.CHAT
    assert logs[0]["insufficient_evidence"] is False
    assert logs[0]["input_tokens"] == 10
    assert logs[0]["output_tokens"] == 20
    assert logs[0]["citation_count"] == 1


async def test_chat_turn_with_insufficient_evidence_records_a_knowledge_gap(
    client_factory,
) -> None:
    # Arrange — no documents seeded.
    client, _ks_id = await _register(client_factory)
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]

    # Act
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_voyage_cls:
        mock_voyage_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post("/chat", json={"query": "Apa isi Pasal 999?"})
    assert response.json()["answer"]["insufficient_evidence"] is True

    # Assert
    async with async_session_factory() as db:
        gaps = (await db.execute(KnowledgeGap.__table__.select())).mappings().all()
    assert len(gaps) == 1
    assert gaps[0]["frequency"] == 1


async def test_knowledge_test_turn_writes_a_query_log_with_test_knowledge_source(
    client_factory,
) -> None:
    # Arrange
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

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        await client.post(
            "/knowledge/test", json={"document_id": str(document_id), "query": "Pasal 7"}
        )

    # Assert
    async with async_session_factory() as db:
        logs = (
            await db.execute(
                QueryLog.__table__.select().where(
                    QueryLog.source == QueryLogSource.TEST_KNOWLEDGE
                )
            )
        ).mappings().all()
    assert len(logs) == 1

    # Test Knowledge traffic must never inflate the real overview dashboard.
    overview = (await client.get("/analytics/overview")).json()
    assert overview["total_questions"] == 0


async def test_owner_can_read_top_questions_and_top_documents(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    document_id = await _seed_article(ks_id)
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

    # Act
    questions_response = await client.get("/analytics/questions")
    sources_response = await client.get("/analytics/sources")

    # Assert
    assert questions_response.status_code == 200
    questions_body = questions_response.json()
    assert len(questions_body) == 1
    assert questions_body[0]["query"] == "Apa isi Pasal 5?"
    assert questions_body[0]["frequency"] == 1
    assert sources_response.status_code == 200
    body = sources_response.json()
    assert body[0]["document_id"] == str(document_id)
    assert body[0]["citation_count"] == 1


async def test_viewer_cannot_read_top_questions_or_top_documents(client_factory) -> None:
    # Arrange
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer2@analytics-endpoint.io", "VIEWER")
    await viewer_client.post(
        "/auth/login",
        json={"email": "viewer2@analytics-endpoint.io", "password": "supersecret123"},
    )

    # Act / Assert
    assert (await viewer_client.get("/analytics/questions")).status_code == 403
    assert (await viewer_client.get("/analytics/sources")).status_code == 403


async def test_owner_can_read_overview_and_knowledge_gaps(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

    # Act
    overview_response = await client.get("/analytics/overview")
    gaps_response = await client.get("/analytics/knowledge-gaps")

    # Assert
    assert overview_response.status_code == 200
    body = overview_response.json()
    assert body["total_questions"] == 1
    assert body["answered"] == 1
    assert gaps_response.status_code == 200
    assert gaps_response.json() == []


async def test_viewer_cannot_read_overview(client_factory) -> None:
    # Arrange
    owner_client, viewer_client = client_factory(), client_factory()
    await owner_client.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner_client, "viewer@analytics-endpoint.io", "VIEWER")
    await viewer_client.post(
        "/auth/login", json={"email": "viewer@analytics-endpoint.io", "password": "supersecret123"}
    )

    # Act
    response = await viewer_client.get("/analytics/overview")

    # Assert
    assert response.status_code == 403


async def test_user_can_submit_feedback_on_own_message(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
    conversation_id = response.json()["conversation_id"]
    detail = (await client.get(f"/conversations/{conversation_id}")).json()
    assistant_message_id = next(
        m["id"] for m in detail["messages"] if m["role"] == "ASSISTANT"
    )

    # Act
    feedback_response = await client.post(
        f"/messages/{assistant_message_id}/feedback",
        json={"rating": "THUMBS_UP", "comment": "Helpful"},
    )

    # Assert
    assert feedback_response.status_code == 200
    body = feedback_response.json()
    assert body["rating"] == "THUMBS_UP"
    assert body["message_id"] == assistant_message_id


async def test_user_cannot_submit_feedback_on_another_users_message(client_factory) -> None:
    # Arrange — two different orgs/users (simplest way to get two distinct
    # users in this test setup, same as test_chat.py's cross-user test).
    client_a, ks_id_a = await _register(client_factory, REGISTER_PAYLOAD)
    await _seed_article(ks_id_a)
    client_b, _ks_id_b = await _register(
        client_factory,
        {
            "organization_name": "Analytics Endpoint Org B",
            "email": "owner@analytics-endpoint-b.io",
            "password": "supersecret123",
        },
    )
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client_a.post("/chat", json={"query": "Apa isi Pasal 5?"})
    conversation_id = response.json()["conversation_id"]
    detail = (await client_a.get(f"/conversations/{conversation_id}")).json()
    assistant_message_id = next(
        m["id"] for m in detail["messages"] if m["role"] == "ASSISTANT"
    )

    # Act
    forbidden = await client_b.post(
        f"/messages/{assistant_message_id}/feedback", json={"rating": "THUMBS_DOWN"}
    )

    # Assert
    assert forbidden.status_code == 404
