from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.core.security import hash_password
from app.organizations.models import OrganizationMember, OrgRole
from app.organizations.schemas import MemberCreateRequest, MemberPublic
from app.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("/members", response_model=MemberPublic, status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: MemberCreateRequest,
    membership: OrganizationMember = Depends(require_role(OrgRole.OWNER, OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MemberPublic:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    new_membership = OrganizationMember(
        organization_id=membership.organization_id,
        user_id=user.id,
        role=payload.role,
    )
    db.add(new_membership)
    await db.flush()

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="member_create",
        entity_type="organization_member",
        entity_id=new_membership.id,
        new_value={"role": payload.role.value},
    )
    await db.commit()

    return MemberPublic(
        id=new_membership.id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=new_membership.role,
        created_at=new_membership.created_at,
    )


@router.get("/members", response_model=list[MemberPublic])
async def list_members(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[MemberPublic]:
    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == membership.organization_id)
    )
    return [
        MemberPublic(
            id=member.id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            created_at=member.created_at,
        )
        for member, user in result.all()
    ]
