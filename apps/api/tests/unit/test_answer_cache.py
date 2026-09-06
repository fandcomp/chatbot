"""Unit tests for AnswerCacheService (spec §45/§47 rule 9) against the real
Redis instance (`docker compose up -d`) — mirrors how tests/unit/
test_structure_rbac.py hits real Postgres directly rather than mocking.
"""

import uuid

import pytest_asyncio

from app.caching.answer_cache import AnswerCacheService
from app.citations.schemas import Citation
from app.core.config import settings
from app.core.redis_client import redis_client
from app.llm.answer_schemas import QueryIntent
from app.verification.schemas import AnswerResponse


@pytest_asyncio.fixture(autouse=True)
async def _clean_answer_cache():
    yield
    async for key in redis_client.scan_iter(match="answer_cache:*"):
        await redis_client.delete(key)


def _answer(summary: str = "Setiap warga negara berhak atas pendidikan dasar.") -> AnswerResponse:
    return AnswerResponse(
        query="Apa isi Pasal 5?",
        tier="FAST",
        retrieval_mode="EXACT_STRUCTURAL",
        reranked=False,
        insufficient_evidence=False,
        reason_if_insufficient=None,
        answer_type=QueryIntent.FACTUAL_LOOKUP,
        summary=summary,
        sections=[],
        claims=[],
        citations={
            "S1": Citation(
                source_id="S1",
                document_id=uuid.uuid4(),
                document_title="Test Regulation",
                structural_path_text="Pasal 5",
                page_start=1,
                page_end=1,
                original_text_excerpt="Setiap warga negara berhak atas pendidikan dasar.",
            )
        },
    )


def _sources() -> list[dict]:
    return [
        {
            "source_label": "S1",
            "chunk_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "structural_path_text": "Pasal 5",
            "page_start": 1,
            "page_end": 1,
        }
    ]


async def test_get_returns_none_for_a_cold_key() -> None:
    # Arrange
    service = AnswerCacheService()
    org_id, chatbot_id = uuid.uuid4(), uuid.uuid4()

    # Act / Assert
    assert await service.get(org_id, chatbot_id, "Apa isi Pasal 5?") is None


async def test_set_then_get_round_trips_the_answer_and_sources() -> None:
    # Arrange
    service = AnswerCacheService()
    org_id, chatbot_id = uuid.uuid4(), uuid.uuid4()
    answer, sources = _answer(), _sources()

    # Act
    await service.set(org_id, chatbot_id, "Apa isi Pasal 5?", answer, sources)
    cached = await service.get(org_id, chatbot_id, "Apa isi Pasal 5?")

    # Assert
    assert cached is not None
    cached_answer, cached_sources = cached
    assert cached_answer.summary == answer.summary
    assert cached_sources[0]["chunk_id"] == sources[0]["chunk_id"]
    assert isinstance(cached_sources[0]["chunk_id"], uuid.UUID)


async def test_lookup_is_normalized_and_org_chatbot_scoped() -> None:
    # Arrange — case/whitespace-insensitive within the same org+chatbot.
    service = AnswerCacheService()
    org_id, chatbot_id = uuid.uuid4(), uuid.uuid4()
    await service.set(org_id, chatbot_id, "Apa isi Pasal 5?", _answer(), _sources())

    # Act / Assert
    assert await service.get(org_id, chatbot_id, "  apa ISI pasal 5?  ") is not None
    # A different org must never see another org's cached answer.
    assert await service.get(uuid.uuid4(), chatbot_id, "Apa isi Pasal 5?") is None


async def test_invalidate_organization_clears_all_of_that_orgs_entries() -> None:
    # Arrange
    service = AnswerCacheService()
    org_id, chatbot_id = uuid.uuid4(), uuid.uuid4()
    other_org_id = uuid.uuid4()
    await service.set(org_id, chatbot_id, "Apa isi Pasal 5?", _answer(), _sources())
    await service.set(other_org_id, chatbot_id, "Apa isi Pasal 5?", _answer(), _sources())

    # Act
    await service.invalidate_organization(org_id)

    # Assert
    assert await service.get(org_id, chatbot_id, "Apa isi Pasal 5?") is None
    assert await service.get(other_org_id, chatbot_id, "Apa isi Pasal 5?") is not None


async def test_disabled_flag_short_circuits_get_and_set(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_CACHE", False)
    service = AnswerCacheService()
    org_id, chatbot_id = uuid.uuid4(), uuid.uuid4()

    # Act
    await service.set(org_id, chatbot_id, "Apa isi Pasal 5?", _answer(), _sources())

    # Assert
    assert await service.get(org_id, chatbot_id, "Apa isi Pasal 5?") is None
