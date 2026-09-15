"""M11 backend: conversation persistence, session memory (§43), and the
POST /chat / POST /chat/stream generation endpoints. HF/Voyage always
mocked — no real Groq/HF/Voyage call.

Requires `docker compose up -d` to be running from the repo root.
"""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.chat.chat_service import _INSUFFICIENT_EVIDENCE_MESSAGE
from app.citations.service import AdaptiveCitationService
from app.core.config import settings
from app.core.database import async_session_factory
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Chat Test Org",
    "email": "owner@chat-test.io",
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


async def _seed_article(ks_id: str, text: str = "Pasal 5\nSetiap warga negara berhak atas pendidikan dasar."):
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
            original_text=text,
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 5", "title": None}],
            structural_path_text="Pasal 5",
            article_number="5",
        )
        await db.commit()


async def test_chat_creates_conversation_and_persists_both_turns(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]["insufficient_evidence"] is False
    conversation_id = body["conversation_id"]

    detail = (await client.get(f"/conversations/{conversation_id}")).json()
    assert detail["title"] == "Apa isi Pasal 5?"
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "USER"
    assert detail["messages"][1]["role"] == "ASSISTANT"


async def test_second_turn_includes_conversation_context(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Both turns cite Pasal 5 by name, so both stay on the exact-match path
    # (no Voyage call) — an insufficient-evidence turn would short-circuit
    # before ever reaching the LLM, which would defeat this test's point.
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )

        first = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
        conversation_id = first.json()["conversation_id"]

        second = await client.post(
            "/chat",
            json={"query": "Jelaskan lebih lanjut Pasal 5.", "conversation_id": conversation_id},
        )
        # Act — inspect what the second LLM call actually received.
        second_call_messages = mock_client_cls.return_value.chat_completion.call_args_list[1].kwargs[
            "messages"
        ]

    # Assert
    assert second.status_code == 200
    user_message_content = second_call_messages[1]["content"]
    assert "CONVERSATION CONTEXT" in user_message_content
    assert "Apa isi Pasal 5?" in user_message_content

    detail = (await client.get(f"/conversations/{conversation_id}")).json()
    assert len(detail["messages"]) == 4


async def test_two_conversations_do_not_leak_context_into_each_other(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Neither query has a parseable legal reference, so both fall through
    # to hybrid search — mock Voyage too (M7's own convention).
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]

    with (
        patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls,
        patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_voyage_cls,
    ):
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        mock_voyage_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)

        first = await client.post("/chat", json={"query": "Pertanyaan percakapan A"})
        second = await client.post("/chat", json={"query": "Pertanyaan percakapan B"})

    # Assert
    assert first.json()["conversation_id"] != second.json()["conversation_id"]
    conversations = (await client.get("/conversations")).json()
    assert len(conversations) == 2


async def test_user_cannot_access_another_users_conversation(client_factory) -> None:
    # Arrange — two different users registering two different orgs (the
    # simplest way to get two distinct users in this test setup); cross-user
    # isolation within the same org uses the same organization_id+user_id
    # filter, so this also stands in for that case.
    client_a, ks_id_a = await _register(client_factory, REGISTER_PAYLOAD)
    client_b, _ks_id_b = await _register(
        client_factory,
        {
            "organization_name": "Chat Test Org B",
            "email": "owner@chat-test-b.io",
            "password": "supersecret123",
        },
    )
    await _seed_article(ks_id_a)

    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client_a.post("/chat", json={"query": "Apa isi Pasal 5?"})
    conversation_id = response.json()["conversation_id"]

    # Act
    forbidden = await client_b.get(f"/conversations/{conversation_id}")

    # Assert
    assert forbidden.status_code == 404


async def test_rename_and_delete_conversation(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(
            return_value=_completion(_STRUCTURED_ANSWER)
        )
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})
    conversation_id = response.json()["conversation_id"]

    # Act
    renamed = await client.patch(
        f"/conversations/{conversation_id}", json={"title": "Custom title"}
    )
    deleted = await client.delete(f"/conversations/{conversation_id}")
    after_delete = await client.get(f"/conversations/{conversation_id}")

    # Assert
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Custom title"
    assert deleted.status_code == 204
    assert after_delete.status_code == 404


async def test_chat_with_no_evidence_returns_insufficient_evidence(client_factory) -> None:
    # Arrange — no documents seeded.
    client, _ks_id = await _register(client_factory)

    # Act — hybrid fallback still calls Voyage for query embedding even
    # against an empty index (M7's own convention).
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_voyage_cls:
        mock_voyage_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post("/chat", json={"query": "Apa isi Pasal 999?"})

    # Assert
    assert response.status_code == 200
    assert response.json()["answer"]["insufficient_evidence"] is True


async def test_chat_stream_yields_tokens_and_a_final_sources_event(client_factory) -> None:
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    async def _fake_stream(*, messages, model, stream=False, **kwargs):
        async def gen():
            for word in ("Setiap warga negara berhak atas pendidikan. ", "[S1]"):
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=word))]
                )

        return gen()

    # Act
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(side_effect=_fake_stream)
        async with client.stream(
            "POST", "/chat/stream", json={"query": "Apa isi Pasal 5?"}
        ) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk

    # Assert
    assert response.status_code == 200
    text = body.decode()
    # ADR-022: stream_answer buffers the full LLM response, verifies it,
    # then re-chunks the (possibly redacted) text word-by-word to
    # reconstruct a "typing" effect — no longer a passthrough of the raw
    # LLM chunk boundaries, so assert on the reconstructed full text
    # rather than one specific chunk.
    token_section = text.split("event: sources", 1)[0]
    reconstructed = "".join(
        block[len("data: ") :] for block in token_section.split("\n\n") if block.startswith("data: ")
    )
    assert reconstructed == "Setiap warga negara berhak atas pendidikan. [S1]"
    assert "event: sources" in text
    assert '"claims"' in text

    sources_data = text.split("event: sources\ndata: ", 1)[1].split("\n\n", 1)[0]
    sources_payload = json.loads(sources_data)
    # Feedback (M14) needs a real persisted Message id to submit against —
    # never the frontend's client-generated streaming placeholder id.
    assert sources_payload["message_id"]
    async with async_session_factory() as db:
        from app.chat.models import Message

        message = await db.get(Message, uuid.UUID(sources_payload["message_id"]))
        assert message is not None
        assert message.role.value == "ASSISTANT"


async def test_chat_stream_redacts_an_unsupported_fabricated_claim(client_factory) -> None:
    # ADR-022 regression: a claim that fabricates "Pasal" terminology for a
    # source that only has a numbered section (addendum §34) must never
    # reach the user — this is the streaming-path equivalent of
    # test_verification_answer.py's non-streaming UNSUPPORTED test, proving
    # the fix works on the ONLY path apps/web actually calls.
    client, ks_id = await _register(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.NUMBERED_SECTION,
            sequence_number=0,
            original_text="11. Urut-urutan Kegiatan wajib dilaksanakan.",
            structural_path_json=[{"type": "NUMBERED_SECTION", "label": "11", "title": None}],
            structural_path_text="BAB III > 11 Urut-urutan Kegiatan",
            number_raw="11.",
            number_normalized="11",
        )
        await db.commit()

    fabricated_text = "Berdasarkan Pasal 11, kegiatan tersebut wajib dilaksanakan. [S1]"

    async def _fake_stream(*, messages, model, stream=False, **kwargs):
        async def gen():
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=fabricated_text))])

        return gen()

    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(side_effect=_fake_stream)
        async with client.stream("POST", "/chat/stream", json={"query": "angka 11"}) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk

    assert response.status_code == 200
    text = body.decode()
    token_section = text.split("event: sources", 1)[0]
    reconstructed = "".join(
        block[len("data: ") :] for block in token_section.split("\n\n") if block.startswith("data: ")
    )
    # The fabricated sentence must be gone entirely — not truncated, not
    # partially redacted, and the answer as a whole must present as
    # insufficient evidence rather than a fabricated one masquerading as
    # a real (if incomplete) answer.
    assert "Pasal 11" not in reconstructed
    assert reconstructed == _INSUFFICIENT_EVIDENCE_MESSAGE

    sources_data = text.split("event: sources\ndata: ", 1)[1].split("\n\n", 1)[0]
    sources_payload = json.loads(sources_data)
    assert sources_payload["insufficient_evidence"] is True
    assert sources_payload["citations"] == {}
    assert sources_payload["claims"][0]["status"] == "UNSUPPORTED"

    async with async_session_factory() as db:
        from app.chat.models import Message

        message = await db.get(Message, uuid.UUID(sources_payload["message_id"]))
        assert message is not None
        assert "Pasal 11" not in message.content


async def test_citation_building_starts_before_llm_generation_finishes(client_factory) -> None:
    """Gap audit 2026-09-15 (performance pass, finding #6): build_citations
    only ever depends on evidence already in hand, so ChatService.answer()
    starts it concurrently with the LLM call instead of waiting for the LLM
    to finish first. Proven here by blocking the mocked LLM call until
    citations has already started — under the old sequential code this
    would deadlock (citations never even attempted until after the LLM
    call returns) instead of completing.
    """
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    citations_started = asyncio.Event()
    real_build_citations = AdaptiveCitationService.build_citations

    async def _tracking_build_citations(self, evidence, organization_id):
        citations_started.set()
        return await real_build_citations(self, evidence, organization_id)

    async def _blocking_chat_completion(*args, **kwargs):
        await asyncio.wait_for(citations_started.wait(), timeout=2)
        return _completion(_STRUCTURED_ANSWER)

    # Act
    with (
        patch.object(AdaptiveCitationService, "build_citations", _tracking_build_citations),
        patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls,
    ):
        mock_client_cls.return_value.chat_completion = AsyncMock(
            side_effect=_blocking_chat_completion
        )
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 200
    assert citations_started.is_set()
    assert response.json()["answer"]["citations"]


async def test_llm_failure_still_surfaces_as_an_error_despite_the_concurrent_citations_task(
    client_factory,
) -> None:
    """The exception-priority half of the same fix: an LLM failure must
    still fail the whole request exactly as before, even though a citations
    task is now running concurrently with it.
    """
    # Arrange
    client, ks_id = await _register(client_factory)
    await _seed_article(ks_id)

    # Act — every model (primary and fallback) fails.
    with patch("app.llm.gateway.AsyncInferenceClient") as mock_client_cls:
        mock_client_cls.return_value.chat_completion = AsyncMock(side_effect=RuntimeError("down"))
        response = await client.post("/chat", json={"query": "Apa isi Pasal 5?"})

    # Assert
    assert response.status_code == 502
