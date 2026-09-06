"""TestKnowledgeService (spec §61/§90) — lets an admin preview answer
quality for ONE specific document before/around publish, using the exact
same Retrieval -> Reranking -> Context -> LLM -> Verification -> Citation
chain as real chat (ChatService), scoped to a single document_id instead of
the org-wide ACTIVE filter (see RetrievalService.retrieve's document_id
param) so a document still in review can be tested.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.citations.service import AdaptiveCitationService
from app.knowledge.schemas import RetrievedSourcePreview, TestKnowledgeResponse
from app.llm.answer_schemas import QueryIntent
from app.llm.answer_service import AnswerGenerationService
from app.llm.model_router import choose_model_tier
from app.reranking.service import RerankingService
from app.retrieval.service import RetrievalService
from app.verification.service import ClaimVerificationService

_INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Informasi tersebut belum ditemukan pada dokumen yang tersedia dalam "
    "basis pengetahuan saat ini."
)


class TestKnowledgeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._retrieval = RetrievalService(db)
        self._reranking = RerankingService(db)
        self._citations = AdaptiveCitationService(db)
        self._verification = ClaimVerificationService()

    async def test(
        self, organization_id: uuid.UUID, document_id: uuid.UUID, query: str
    ) -> TestKnowledgeResponse:
        retrieval_response = await self._retrieval.retrieve(
            organization_id=organization_id, query=query, document_id=document_id
        )
        evidence_response = await self._reranking.select_evidence(retrieval_response)

        retrieved_sources = [
            RetrievedSourcePreview(
                chunk_id=item.chunk_id,
                structural_path_text=item.structural_path_text,
                original_text=item.original_text,
                score=item.relevance_score,
            )
            for item in evidence_response.evidence
        ]

        if not evidence_response.evidence:
            return TestKnowledgeResponse(
                question=query,
                detected_intent=QueryIntent.OTHER,
                retrieval_mode=evidence_response.retrieval_mode,
                retrieved_sources=[],
                answer=_INSUFFICIENT_EVIDENCE_MESSAGE,
                insufficient_evidence=True,
                reason_if_insufficient=_INSUFFICIENT_EVIDENCE_MESSAGE,
                citations={},
            )

        distinct_document_count = len({item.document_id for item in evidence_response.evidence})
        tier = choose_model_tier(query, distinct_document_count)

        structured_answer = await AnswerGenerationService().generate_answer(
            query, evidence_response.evidence, tier
        )
        # Verification runs so the preview reflects the same guardrails a
        # real answer would go through, but this endpoint surfaces the
        # answer text either way — it's a quality preview, not a gate.
        self._verification.verify(structured_answer.claims, evidence_response.evidence)
        citations = await self._citations.build_citations(evidence_response.evidence)

        return TestKnowledgeResponse(
            question=query,
            detected_intent=structured_answer.answer_type,
            retrieval_mode=evidence_response.retrieval_mode,
            retrieved_sources=retrieved_sources,
            answer=structured_answer.summary,
            insufficient_evidence=structured_answer.insufficient_evidence,
            reason_if_insufficient=structured_answer.reason_if_insufficient,
            citations=citations,
        )
