import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.knowledge.models import KnowledgeSpace
from app.knowledge.schemas import KnowledgeSpaceCreateRequest, KnowledgeSpacePublic
from app.organizations.models import OrganizationMember, OrgRole

router = APIRouter(prefix="/knowledge-spaces", tags=["knowledge"])


async def _get_org_scoped_space(
    db: AsyncSession, space_id: uuid.UUID, organization_id: uuid.UUID
) -> KnowledgeSpace:
    result = await db.execute(
        select(KnowledgeSpace).where(
            KnowledgeSpace.id == space_id, KnowledgeSpace.organization_id == organization_id
        )
    )
    space = result.scalar_one_or_none()
    if space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge space not found")
    return space


@router.post("", response_model=KnowledgeSpacePublic, status_code=status.HTTP_201_CREATED)
async def create_knowledge_space(
    payload: KnowledgeSpaceCreateRequest,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSpacePublic:
    space = KnowledgeSpace(organization_id=membership.organization_id, name=payload.name)
    db.add(space)
    await db.flush()

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="knowledge_space_create",
        entity_type="knowledge_space",
        entity_id=space.id,
        new_value={"name": space.name},
    )
    await db.commit()

    return KnowledgeSpacePublic.model_validate(space)


@router.get("", response_model=list[KnowledgeSpacePublic])
async def list_knowledge_spaces(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeSpacePublic]:
    result = await db.execute(
        select(KnowledgeSpace).where(KnowledgeSpace.organization_id == membership.organization_id)
    )
    return [KnowledgeSpacePublic.model_validate(space) for space in result.scalars().all()]


@router.get("/{space_id}", response_model=KnowledgeSpacePublic)
async def get_knowledge_space(
    space_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSpacePublic:
    space = await _get_org_scoped_space(db, space_id, membership.organization_id)
    return KnowledgeSpacePublic.model_validate(space)


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_space(
    space_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(OrgRole.OWNER, OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    space = await _get_org_scoped_space(db, space_id, membership.organization_id)

    # Documents FK-reference knowledge_spaces without ON DELETE CASCADE, so a
    # space that still has documents fails the DB constraint. We surface that
    # as a clear 409 instead of a raw IntegrityError.
    from app.documents.models import (
        Document,  # local import avoids a cycle at module load
    )

    existing = await db.execute(select(Document.id).where(Document.knowledge_space_id == space_id))
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a knowledge space that still has documents.",
        )

    await db.delete(space)
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="knowledge_space_delete",
        entity_type="knowledge_space",
        entity_id=space_id,
    )
    await db.commit()
