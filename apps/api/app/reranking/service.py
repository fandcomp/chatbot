"""RerankingService (spec §90) — M8's slice of §32's pipeline: Confidence
Check -> conditional Voyage Reranker -> Evidence -> Parent Expansion ->
Evidence Extraction. Context Builder and everything LLM-side is M9+.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.reranking.confidence import needs_reranking
from app.reranking.expansion import maybe_expand_with_parent
from app.reranking.reranker_gateway import RerankerGateway
from app.reranking.schemas import Evidence, EvidenceResponse
from app.retrieval.schemas import RetrievalResponse, RetrievedChunk

logger = get_logger(__name__)


class RerankingService:
    def __init__(
        self,
        db: AsyncSession,
        reranker_gateway: RerankerGateway | None = None,
    ) -> None:
        self._db = db
        self._reranker_gateway = reranker_gateway or RerankerGateway()

    async def select_evidence(self, retrieval_response: RetrievalResponse) -> EvidenceResponse:
        chunks = retrieval_response.chunks
        reranked = False
        relevance_scores: list[float | None]

        if needs_reranking(retrieval_response):
            try:
                ranked_pairs = await self._reranker_gateway.rerank(
                    query=retrieval_response.query,
                    candidates=[chunk.original_text for chunk in chunks],
                    top_k=settings.RERANK_TOP_K,
                )
                chunks = [chunks[index] for index, _score in ranked_pairs]
                relevance_scores = [score for _index, score in ranked_pairs]
                reranked = True
            except Exception:  # noqa: BLE001 - a Voyage rerank failure (bad
                # response, timeout, rate limit, network error) must degrade
                # to the un-reranked top RERANK_TOP_K, not fail evidence
                # selection M7 already proved correct.
                logger.warning("reranker_unavailable_falling_back_to_unreranked")
                chunks = chunks[: settings.RERANK_TOP_K]
                relevance_scores = [chunk.score for chunk in chunks]
        else:
            chunks = chunks[: settings.RERANK_TOP_K]
            relevance_scores = [chunk.score for chunk in chunks]

        evidence_list = [
            await self._to_evidence(position, chunk, relevance_score)
            for position, (chunk, relevance_score) in enumerate(
                zip(chunks, relevance_scores, strict=True), start=1
            )
        ]

        return EvidenceResponse(
            query=retrieval_response.query,
            retrieval_mode=retrieval_response.mode,
            reranked=reranked,
            evidence=evidence_list,
        )

    async def _to_evidence(
        self, position: int, chunk: RetrievedChunk, relevance_score: float | None
    ) -> Evidence:
        parent_context = await maybe_expand_with_parent(self._db, chunk)
        return Evidence(
            evidence_id=f"S{position}",
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_version_id=chunk.document_version_id,
            structural_path_text=chunk.structural_path_text,
            original_text=chunk.original_text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            parent_context=parent_context,
            relevance_score=relevance_score,
        )
