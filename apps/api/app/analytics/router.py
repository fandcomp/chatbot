import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import Feedback
from app.analytics.schemas import (
    AnalyticsOverview,
    FeedbackPublic,
    FeedbackRequest,
    KnowledgeGapPublic,
)
from app.analytics.service import AnalyticsService
from app.auth.dependencies import require_role
from app.chat.models import Conversation, Message
from app.core.database import get_db
from app.organizations.models import OrganizationMember, OrgRole

analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
feedback_router = APIRouter(tags=["analytics"])

# Analytics dashboards are an admin capability, matching Test Knowledge's
# RBAC (§52) — VIEWERs chat but don't see aggregate usage/cost data.
_ANALYTICS_ROLES = (OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)


@analytics_router.get("/overview", response_model=AnalyticsOverview)
async def get_overview(
    membership: OrganizationMember = Depends(require_role(*_ANALYTICS_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    service = AnalyticsService(db)
    return await service.get_overview(membership.organization_id)


@analytics_router.get("/knowledge-gaps", response_model=list[KnowledgeGapPublic])
async def get_knowledge_gaps(
    membership: OrganizationMember = Depends(require_role(*_ANALYTICS_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeGapPublic]:
    service = AnalyticsService(db)
    gaps = await service.list_knowledge_gaps(membership.organization_id)
    return [
        KnowledgeGapPublic(
            query=gap.sample_query_text, frequency=gap.frequency, last_asked_at=gap.last_asked_at
        )
        for gap in gaps
    ]


@feedback_router.post("/messages/{message_id}/feedback", response_model=FeedbackPublic)
async def submit_feedback(
    message_id: uuid.UUID,
    body: FeedbackRequest,
    membership: OrganizationMember = Depends(require_role(*_ANALYTICS_ROLES, OrgRole.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> FeedbackPublic:
    # A message only belongs to a conversation this exact user owns (chat
    # history is per-user even within a shared org, per M11's own design).
    message = (
        await db.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.id == message_id,
                Conversation.organization_id == membership.organization_id,
                Conversation.user_id == membership.user_id,
            )
        )
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    feedback = Feedback(
        organization_id=membership.organization_id,
        message_id=message_id,
        user_id=membership.user_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return FeedbackPublic(
        id=feedback.id, message_id=feedback.message_id, rating=feedback.rating, comment=feedback.comment
    )
