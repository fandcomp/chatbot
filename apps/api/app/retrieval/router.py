import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.core.config import settings
from app.core.database import get_db
from app.knowledge.models import KnowledgeSpace
from app.organizations.models import OrganizationMember, OrgRole
from app.retrieval.exceptions import RetrievalTimeout
from app.retrieval.schemas import RetrievalRequest, RetrievalResponse
from app.retrieval.service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalResponse)
async def search(
    body: RetrievalRequest,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> RetrievalResponse:
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

    service = RetrievalService(db)
    try:
        return await asyncio.wait_for(
            service.retrieve(
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
