"""LAN-M1 admin API (docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md) — register a
source, list sources, trigger a catalog-only discovery scan, and inspect
scan/entry status. Every endpoint is tenant-scoped and role-gated from this
first milestone — security is never deferred to a later one.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.core.tasks import enqueue_scan_source
from app.organizations.models import OrganizationMember, OrgRole
from app.sources.models import ScanRun, ScanRunStatus, SourceEntry, SourceRoot
from app.sources.schemas import (
    CreateSourceRequest,
    ScanRunPublic,
    SourceEntryPublic,
    SourceRootPublic,
    TriggerScanResponse,
)

router = APIRouter(prefix="/sources", tags=["sources"])

_MANAGE_ROLES = (OrgRole.OWNER, OrgRole.ADMIN)


async def _get_org_scoped_source(
    db: AsyncSession, source_id: uuid.UUID, organization_id: uuid.UUID
) -> SourceRoot:
    result = await db.execute(
        select(SourceRoot).where(
            SourceRoot.id == source_id, SourceRoot.organization_id == organization_id
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


@router.post("", response_model=SourceRootPublic, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: CreateSourceRequest,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> SourceRootPublic:
    source = SourceRoot(
        organization_id=membership.organization_id,
        source_type=payload.source_type,
        display_name=payload.display_name,
        root_path=payload.root_path,
        allowed_subtrees=payload.allowed_subtrees,
        credential_reference=payload.credential_reference,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return SourceRootPublic.model_validate(source, from_attributes=True)


@router.get("", response_model=list[SourceRootPublic])
async def list_sources(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SourceRootPublic]:
    result = await db.execute(
        select(SourceRoot).where(SourceRoot.organization_id == membership.organization_id)
    )
    return [
        SourceRootPublic.model_validate(source, from_attributes=True)
        for source in result.scalars().all()
    ]


@router.post(
    "/{source_id}/scan", response_model=TriggerScanResponse, status_code=status.HTTP_201_CREATED
)
async def trigger_scan(
    source_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> TriggerScanResponse:
    """Enqueues a catalog-only discovery scan — never extracts, embeds, or
    copies file content (LAN-M1 scope, addendum §2)."""
    source = await _get_org_scoped_source(db, source_id, membership.organization_id)

    scan_run = ScanRun(
        organization_id=membership.organization_id,
        source_root_id=source.id,
        status=ScanRunStatus.RUNNING,
    )
    db.add(scan_run)
    await db.commit()
    await db.refresh(scan_run)

    enqueue_scan_source(str(scan_run.id))

    return TriggerScanResponse(scan_run_id=scan_run.id, status=scan_run.status)


@router.get("/{source_id}/scan-runs", response_model=list[ScanRunPublic])
async def list_scan_runs(
    source_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ScanRunPublic]:
    await _get_org_scoped_source(db, source_id, membership.organization_id)
    result = await db.execute(
        select(ScanRun)
        .where(ScanRun.source_root_id == source_id)
        .order_by(ScanRun.started_at.desc())
    )
    return [
        ScanRunPublic.model_validate(scan_run, from_attributes=True)
        for scan_run in result.scalars().all()
    ]


@router.get("/{source_id}/entries", response_model=list[SourceEntryPublic])
async def list_entries(
    source_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[SourceEntryPublic]:
    """Catalog status only — never file content. Paged; callers must not
    assume a single call returns the entire source (addendum §3.1)."""
    await _get_org_scoped_source(db, source_id, membership.organization_id)
    result = await db.execute(
        select(SourceEntry)
        .where(SourceEntry.source_root_id == source_id)
        .order_by(SourceEntry.normalized_path)
        .limit(min(limit, 500))
        .offset(offset)
    )
    return [
        SourceEntryPublic.model_validate(entry, from_attributes=True)
        for entry in result.scalars().all()
    ]
