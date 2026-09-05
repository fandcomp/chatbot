import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.config import settings
from app.core.database import get_db
from app.knowledge.models import KnowledgeSpace
from app.organizations.models import OrganizationMember, OrgRole
from app.reranking.schemas import EvidenceRequest, EvidenceResponse
from app.reranking.service import RerankingService
from app.retrieval.exceptions import RetrievalTimeout
from app.retrieval.service import RetrievalService

router = APIRouter(prefix="/reranking", tags=["reranking"])


@router.post("/evidence", response_model=EvidenceResponse)
async def get_evidence(
    body: EvidenceRequest,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EvidenceResponse:
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
    return await reranking_service.select_evidence(retrieval_response)
