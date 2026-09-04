"""ADR-008's EmbeddingGateway — the worker's only Voyage touchpoint.

Embeds `contextual_text` (not `original_text` — addendum §24.2, ADR-008)
using Voyage's contextualized_embed, which takes one inner list per
*document* (all its chunks together, in order) and returns embeddings
aligned to that same order. `embed_query` (query-time embedding) is a
different process's concern (apps/api, M7) and does not belong here.
"""

import voyageai

from app.core.config import settings


class EmbeddingGateway:
    def __init__(self) -> None:
        self._client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        result = await self._client.contextualized_embed(
            inputs=[texts],
            model=settings.EMBEDDING_MODEL,
            input_type="document",
            output_dimension=settings.VOYAGE_EMBEDDING_DIMENSION,
        )
        return list(result.results[0].embeddings)
