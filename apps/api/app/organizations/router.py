import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.auth.router import limiter, user_or_ip_key
from app.core.database import get_db
from app.core.security import hash_password
from app.organizations.models import OrganizationMember, OrgRole
from app.organizations.schemas import (
    MemberCreateRequest,
    MemberPublic,
    MemberRoleUpdateRequest,
)
from app.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


async def _get_org_scoped_member(
    db: AsyncSession, member_id: uuid.UUID, organization_id: uuid.UUID
) -> tuple[OrganizationMember, User]:
    result = await db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return row


async def _is_last_owner(db: AsyncSession, organization_id: uuid.UUID, member_id: uuid.UUID) -> bool:
    owner_count = (
        await db.execute(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == OrgRole.OWNER,
                OrganizationMember.id != member_id,
            )
        )
    ).scalar_one()
    return owner_count == 0


@router.post("/members", response_model=MemberPublic, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute", key_func=user_or_ip_key)
async def create_member(
    request: Request,
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


@router.patch("/members/{member_id}", response_model=MemberPublic)
@limiter.limit("20/minute", key_func=user_or_ip_key)
async def update_member_role(
    request: Request,
    member_id: uuid.UUID,
    payload: MemberRoleUpdateRequest,
    membership: OrganizationMember = Depends(require_role(OrgRole.OWNER, OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> MemberPublic:
    target_membership, target_user = await _get_org_scoped_member(
        db, member_id, membership.organization_id
    )

    if (
        target_membership.role == OrgRole.OWNER
        and payload.role != OrgRole.OWNER
        and await _is_last_owner(db, membership.organization_id, target_membership.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot change the role of the organization's last OWNER.",
        )

    old_role = target_membership.role
    target_membership.role = payload.role

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="member_role_change",
        entity_type="organization_member",
        entity_id=target_membership.id,
        old_value={"role": old_role.value},
        new_value={"role": payload.role.value},
    )
    await db.commit()
    await db.refresh(target_membership)

    return MemberPublic(
        id=target_membership.id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=target_membership.role,
        created_at=target_membership.created_at,
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute", key_func=user_or_ip_key)
async def remove_member(
    request: Request,
    member_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(OrgRole.OWNER, OrgRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> None:
    target_membership, _target_user = await _get_org_scoped_member(
        db, member_id, membership.organization_id
    )

    if target_membership.role == OrgRole.OWNER and await _is_last_owner(
        db, membership.organization_id, target_membership.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove the organization's last OWNER.",
        )

    old_role = target_membership.role
    await db.delete(target_membership)
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="member_remove",
        entity_type="organization_member",
        entity_id=member_id,
        old_value={"role": old_role.value},
    )
    await db.commit()
