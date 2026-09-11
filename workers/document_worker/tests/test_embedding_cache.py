import pytest

from app.core.config import settings
from app.database import async_session_factory
from app.indexing.embedding_cache import (
    cache_key_for,
    get_cached_embeddings,
    store_embeddings,
)


@pytest.mark.asyncio
async def test_get_cached_embeddings_returns_empty_dict_for_no_keys() -> None:
    async with async_session_factory() as session:
        result = await get_cached_embeddings(session, [])
    assert result == {}


@pytest.mark.asyncio
async def test_store_then_get_cached_embeddings_round_trips() -> None:
    key = cache_key_for("Dokumen: Test. Isi: some contextual text for round trip.")
    embedding = [0.1, 0.2, 0.3]

    async with async_session_factory() as session:
        await store_embeddings(session, [(key, embedding)])

    async with async_session_factory() as session:
        cached = await get_cached_embeddings(session, [key, "not-a-real-key"])

    assert cached == {key: embedding}


@pytest.mark.asyncio
async def test_storing_the_same_key_twice_does_not_error_or_duplicate() -> None:
    key = cache_key_for("Dokumen: Test. Isi: duplicate-store text.")

    async with async_session_factory() as session:
        await store_embeddings(session, [(key, [0.1, 0.2])])
    async with async_session_factory() as session:
        # A second worker racing to cache the same text/config — must no-op,
        # not raise a unique-constraint error.
        await store_embeddings(session, [(key, [0.9, 0.9])])

    async with async_session_factory() as session:
        cached = await get_cached_embeddings(session, [key])

    assert cached[key] == [0.1, 0.2]


def test_cache_key_changes_with_model_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Dokumen: Test. Isi: identical text, different config."
    key_before = cache_key_for(text)

    monkeypatch.setattr(settings, "EMBEDDING_MODEL_REVISION", "2")
    key_after = cache_key_for(text)

    assert key_before != key_after


def test_cache_key_changes_with_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Dokumen: Test. Isi: identical text, different dimension."
    key_before = cache_key_for(text)

    monkeypatch.setattr(settings, "VOYAGE_EMBEDDING_DIMENSION", 256)
    key_after = cache_key_for(text)

    assert key_before != key_after


def test_cache_key_changes_with_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "Dokumen: Test. Isi: identical text, different normalization."
    key_before = cache_key_for(text)

    monkeypatch.setattr(settings, "EMBEDDING_NORMALIZED", not settings.EMBEDDING_NORMALIZED)
    key_after = cache_key_for(text)

    assert key_before != key_after


def test_cache_key_is_stable_for_identical_input() -> None:
    text = "Dokumen: Test. Isi: stability check."
    assert cache_key_for(text) == cache_key_for(text)
