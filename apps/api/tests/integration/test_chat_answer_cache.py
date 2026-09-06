"""M15 answer cache (spec §45/§47 rule 9): a repeated first-turn question
skips retrieval+LLM entirely on the second call, and document archive/delete
invalidate the whole org's cache. HF/Voyage always mocked — no real
Groq/HF/Voyage call.

Requires `docker compose up -d` to be running from the repo root.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest_asyncio

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.redis_client import redis_client
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Answer Cache Org",
    "email": "owner@answer-cache.io",
    "password": "supersecret123",
}


@pytest_asyncio.fixture(autouse=True)
async def _clean_answer_cache():
    yield
    async for key in redis_client.scan_iter(match="answer_cache:*"):
        await redis_client.delete(key)


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


async def _register(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, ks_id


async def _seed_article(ks_id: str) -> str:
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
    return str(document_id)


async def test_repeated_first_turn_question_is_served_from_cache(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Act — two brand-new conversations (both a "first turn"), same question.
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        first = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
        second = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

        # Assert — the LLM was called exactly once; the second turn hit cache.
        assert mock_client_cls.return_value.chat_completion.call_count == 1

    assert first.json()["answer"]["summary"] == second.json()["answer"]["summary"]
    second_detail = (
        await client.get(f"/conversations/{second.json()['conversation_id']}")
    ).json()
    assert len(second_detail["messages"]) == 2


async def test_follow_up_question_in_the_same_conversation_never_uses_cache(
    client_factory,
) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        first = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
        conversation_id = first.json()["conversation_id"]
        await client.post(
            "/chat",
            json={"query": "Apa isi Pasal 5?", "conversation_id": conversation_id},
        )

        # Assert — a same-text follow-up still calls the LLM (context differs).
        assert mock_client_cls.return_value.chat_completion.call_count == 2


async def test_archiving_a_document_invalidates_the_organizations_cache(
    client_factory,
) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    document_id = await _seed_article(ks_id)
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

        # Act
        archive_response = await client.post(f"/documents/{document_id}/archive")
        assert archive_response.status_code == 200

        # Archived means no exact-structural match anymore, so this second
        # call falls through to hybrid search, which still calls Voyage for
        # query embedding even against a now-empty index (M7's own
        # convention, mocked here rather than hitting the real API).
        fake_result = AsyncMock()
        fake_result.results = [
            AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])
        ]
        with patch(
            "app.retrieval.embedding_gateway.voyageai.AsyncClient"
        ) as mock_voyage_cls:
            mock_voyage_cls.return_value.contextualized_embed = AsyncMock(
                return_value=fake_result
            )
            second = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

        # Assert — the archived document must not still answer from cache,
        # and the LLM (still mocked from the first call) is never called a
        # second time since evidence is now empty.
        assert second.json()["answer"]["insufficient_evidence"] is True
        assert mock_client_cls.return_value.chat_completion.call_count == 1
    remaining = [key async for key in redis_client.scan_iter(match="answer_cache:*")]
    assert remaining == []
