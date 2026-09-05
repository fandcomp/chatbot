"""ADR-008's EmbeddingGateway, query side — apps/api's only Voyage
touchpoint (the worker's Voyage touchpoint, embedding_gateway.py, is
document-indexing-only and out of process here).

voyage-context models (EMBEDDING_MODEL=voyage-context-4) require queries go
through `contextualized_embed` too, with the query wrapped as its own
single-item batch and input_type="query" — never the plain `embed()`
endpoint, which is for non-contextual embedding models. Mixing the two would
produce a query vector Qdrant's cosine search never intended to compare
against the indexed contextual document vectors.
"""

import voyageai

from app.core.config import settings


class QueryEmbeddingGateway:
    def __init__(self) -> None:
        self._client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)

    async def embed_query(self, text: str) -> list[float]:
        result = await self._client.contextualized_embed(
            inputs=[[text]],
            model=settings.EMBEDDING_MODEL,
            input_type="query",
            output_dimension=settings.VOYAGE_EMBEDDING_DIMENSION,
        )
        return list(result.results[0].embeddings[0])
