"""ADR-008/spec §37's RerankerGateway — apps/api's only reranking-time
Voyage touchpoint. Business services never see the voyageai SDK directly
(spec §35's gateway pattern).
"""

import voyageai

from app.core.config import settings


class RerankerGateway:
    def __init__(self) -> None:
        self._client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)

    async def rerank(
        self, query: str, candidates: list[str], top_k: int
    ) -> list[tuple[int, float]]:
        """Returns (original_index_into_candidates, relevance_score) pairs,
        already ordered by relevance_score descending (Voyage's own order).
        """
        if not candidates:
            return []
        result = await self._client.rerank(
            query=query, documents=candidates, model=settings.RERANK_MODEL, top_k=top_k
        )
        return [(item.index, item.relevance_score) for item in result.results]
