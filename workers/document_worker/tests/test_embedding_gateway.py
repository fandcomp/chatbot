from unittest.mock import AsyncMock, patch

import pytest

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
