from unittest.mock import AsyncMock, patch

import pytest
from voyageai.error import RateLimitError

from app.indexing.embedding_gateway import EmbeddingGateway


@pytest.mark.asyncio
async def test_embed_documents_calls_voyage_with_document_input_type_and_configured_model() -> None:
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.1, 0.2], [0.3, 0.4]])]

    with patch("app.indexing.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.contextualized_embed = AsyncMock(return_value=fake_result)

        gateway = EmbeddingGateway()
        vectors = await gateway.embed_documents(["chunk one text", "chunk two text"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    mock_client.contextualized_embed.assert_called_once()
    _, kwargs = mock_client.contextualized_embed.call_args
    assert kwargs["inputs"] == [["chunk one text", "chunk two text"]]
    assert kwargs["input_type"] == "document"
    assert kwargs["model"]


@pytest.mark.asyncio
async def test_embed_documents_returns_empty_list_for_no_texts_without_calling_voyage() -> None:
    with patch("app.indexing.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.contextualized_embed = AsyncMock()

        gateway = EmbeddingGateway()
        vectors = await gateway.embed_documents([])

    assert vectors == []
    mock_client.contextualized_embed.assert_not_called()


@pytest.mark.asyncio
async def test_embed_documents_splits_large_document_into_batches_and_preserves_order() -> None:
    # A single unbatched request for a large document reliably exceeds
    # Voyage's per-minute token cap (see embedding_gateway.py's
    # _MAX_CHUNKS_PER_BATCH comment) — this proves the batching that fixes it.
    texts = [f"chunk {i}" for i in range(120)]

    def _fake_result(inputs, **_kwargs):
        batch = inputs[0]
        result = AsyncMock()
        result.results = [AsyncMock(embeddings=[[float(i)] for i in range(len(batch))])]
        return result

    with patch("app.indexing.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.contextualized_embed = AsyncMock(side_effect=_fake_result)

        gateway = EmbeddingGateway()
        vectors = await gateway.embed_documents(texts)

    assert mock_client.contextualized_embed.call_count == 3  # 50 + 50 + 20
    batch_sizes = [
        len(call.kwargs["inputs"][0]) for call in mock_client.contextualized_embed.call_args_list
    ]
    assert batch_sizes == [50, 50, 20]
    assert len(vectors) == 120


@pytest.mark.asyncio
async def test_embed_documents_retries_a_rate_limited_batch_after_a_fixed_wait() -> None:
    # The free tier's 3-requests-per-minute cap means batch 2 can 429 right
    # after batch 1 succeeds — retrying just that batch (not the whole
    # document) after a real wait is what actually clears the window.
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.5]])]

    with patch("app.indexing.embedding_gateway.voyageai.AsyncClient") as mock_client_cls, patch(
        "app.indexing.embedding_gateway.asyncio.sleep", new_callable=AsyncMock
    ) as mock_sleep:
        mock_client = mock_client_cls.return_value
        mock_client.contextualized_embed = AsyncMock(
            side_effect=[RateLimitError("rate limited"), fake_result]
        )

        gateway = EmbeddingGateway()
        vectors = await gateway.embed_documents(["chunk one"])

    assert vectors == [[0.5]]
    assert mock_client.contextualized_embed.call_count == 2
    mock_sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_documents_raises_after_exhausting_rate_limit_retries() -> None:
    with patch("app.indexing.embedding_gateway.voyageai.AsyncClient") as mock_client_cls, patch(
        "app.indexing.embedding_gateway.asyncio.sleep", new_callable=AsyncMock
    ):
        mock_client = mock_client_cls.return_value
        mock_client.contextualized_embed = AsyncMock(
            side_effect=RateLimitError("rate limited")
        )

        gateway = EmbeddingGateway()
        with pytest.raises(RateLimitError):
            await gateway.embed_documents(["chunk one"])

    assert mock_client.contextualized_embed.call_count == 4  # _RATE_LIMIT_MAX_ATTEMPTS
