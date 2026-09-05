import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.citations.service import AdaptiveCitationService
from app.core.config import settings
from app.core.database import get_db
from app.knowledge.models import KnowledgeSpace
from app.llm.answer_schemas import QueryIntent
from app.llm.answer_service import AnswerGenerationService
from app.llm.exceptions import LLMProviderUnavailable
from app.llm.model_router import choose_model_tier
from app.organizations.models import OrganizationMember, OrgRole
from app.reranking.service import RerankingService
from app.retrieval.exceptions import RetrievalTimeout
from app.retrieval.service import RetrievalService
from app.verification.schemas import AnswerRequest, AnswerResponse
from app.verification.service import ClaimVerificationService

router = APIRouter(prefix="/verification", tags=["verification"])

# spec §31.3's canonical "not found" phrasing.
_INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Informasi tersebut belum ditemukan pada dokumen yang tersedia dalam "
    "basis pengetahuan saat ini."
)


@router.post("/answer", response_model=AnswerResponse)
async def answer(
    body: AnswerRequest,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    if body.knowledge_space_id is not None:
        knowledge_space = (
            await db.execute(
                select(KnowledgeSpace).where(
                    KnowledgeSpace.id == body.knowledge_space_id,
                    KnowledgeSpace.organization_id == membership.organization_id,
                )
            )
        ).scalar_one_or_none()
        if knowledge_space is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge space not found"
            )

    retrieval_service = RetrievalService(db)
    try:
        retrieval_response = await asyncio.wait_for(
            retrieval_service.retrieve(
                organization_id=membership.organization_id,
                query=body.query,
                knowledge_space_id=body.knowledge_space_id,
            ),
            timeout=settings.RETRIEVAL_TIMEOUT,
        )
    except (TimeoutError, RetrievalTimeout) as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Retrieval timed out"
        ) from exc

    reranking_service = RerankingService(db)
    evidence_response = await reranking_service.select_evidence(retrieval_response)

    if not evidence_response.evidence:
        # No evidence at all — never let the LLM guess (ADR-010).
        return AnswerResponse(
            query=body.query,
            tier="FAST",
            retrieval_mode=evidence_response.retrieval_mode,
            reranked=evidence_response.reranked,
            insufficient_evidence=True,
            reason_if_insufficient=_INSUFFICIENT_EVIDENCE_MESSAGE,
            answer_type=QueryIntent.OTHER,
            summary="",
            sections=[],
            claims=[],
            citations={},
        )

    distinct_document_count = len(
        {item.document_id for item in evidence_response.evidence}
    )
    tier = choose_model_tier(body.query, distinct_document_count)

    answer_service = AnswerGenerationService()
    try:
        structured_answer = await answer_service.generate_answer(
            body.query, evidence_response.evidence, tier
        )
    except LLMProviderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    verification_service = ClaimVerificationService()
    verified_claims = verification_service.verify(
        structured_answer.claims, evidence_response.evidence
    )

    citation_service = AdaptiveCitationService(db)
    citations = await citation_service.build_citations(evidence_response.evidence)

    return AnswerResponse(
        query=body.query,
        tier=tier,
        retrieval_mode=evidence_response.retrieval_mode,
        reranked=evidence_response.reranked,
        insufficient_evidence=structured_answer.insufficient_evidence,
        reason_if_insufficient=structured_answer.reason_if_insufficient,
        answer_type=structured_answer.answer_type,
        summary=structured_answer.summary,
        sections=structured_answer.sections,
        claims=verified_claims,
        citations=citations,
    )
