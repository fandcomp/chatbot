import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, get_current_user
from app.auth.schemas import LoginRequest, MePublic, RegisterRequest, UserPublic
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    _DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.organizations.models import Organization, OrganizationMember, OrgRole
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "org"


async def _unique_slug(db: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 0
    while True:
        result = await db.execute(select(Organization).where(Organization.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        suffix += 1
        slug = f"{base_slug}-{suffix}"


def _set_session_cookie(response: Response, user_id: uuid.UUID) -> None:
    token = create_access_token({"sub": str(user_id)})
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=MePublic, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> MePublic:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    slug = await _unique_slug(db, _slugify(payload.organization_name))
    organization = Organization(name=payload.organization_name, slug=slug)
    db.add(organization)
    await db.flush()

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()

    membership = OrganizationMember(
        organization_id=organization.id,
        user_id=user.id,
        role=OrgRole.OWNER,
    )
    db.add(membership)
    await db.flush()

    await log_action(
        db,
        actor_id=user.id,
        organization_id=organization.id,
        action="register",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()

    _set_session_cookie(response, user.id)

    return MePublic(
        user=UserPublic.model_validate(user),
        organization_id=organization.id,
        role=membership.role,
    )


@router.post("/login", response_model=MePublic)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> MePublic:
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
    )

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    # Always run a real bcrypt comparison, even for an unknown email, so a
    # missing account isn't distinguishable from a wrong password by timing.
    password_ok = verify_password(payload.password, user.hashed_password if user else _DUMMY_HASH)
    if user is None or not user.is_active or not password_ok:
        raise invalid_credentials

    membership_result = await db.execute(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        raise invalid_credentials

    await log_action(
        db,
        actor_id=user.id,
        organization_id=membership.organization_id,
        action="login",
        entity_type="user",
        entity_id=user.id,
    )
    await db.commit()

    _set_session_cookie(response, user.id)

    return MePublic(
        user=UserPublic.model_validate(user),
        organization_id=membership.organization_id,
        role=membership.role,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    _user: User = Depends(get_current_user),
) -> None:
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)


@router.get("/me", response_model=MePublic)
async def me(
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_current_membership),
) -> MePublic:
    return MePublic(
        user=UserPublic.model_validate(user),
        organization_id=membership.organization_id,
        role=membership.role,
    )
