"""LAN-M1/M2 admin API (docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md) — register a
source, list sources, trigger a catalog-only discovery scan, inspect scan/
entry status, and (LAN-M2) promote selected catalog entries into the
existing document pipeline. Every endpoint is tenant-scoped and role-gated
from the first milestone — security is never deferred to a later one.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.core.tasks import enqueue_promote_source_entry, enqueue_scan_source
from app.knowledge.models import KnowledgeSpace
from app.organizations.models import OrganizationMember, OrgRole
from app.sources.models import (
    PromotionRecord,
    PromotionStatus,
    ScanRun,
    ScanRunStatus,
    SourceEntry,
    SourceRoot,
)
from app.sources.schemas import (
    CreateSourceRequest,
    PromoteEntriesRequest,
    PromoteEntriesResponse,
    PromotionRecordPublic,
    ScanRunPublic,
    SourceEntryPublic,
    SourceRootPublic,
    TriggerScanResponse,
)

router = APIRouter(prefix="/sources", tags=["sources"])

_MANAGE_ROLES = (OrgRole.OWNER, OrgRole.ADMIN)
# Lock/temp files a LAN scan can legitimately catalog but must never promote
# (addendum §6 — "abaikan file lock/temp seperti ~$*.docx").
_SKIP_PROMOTION_PATTERNS = (re.compile(r"(^|/)~\$"), re.compile(r"\.tmp$", re.IGNORECASE))


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


def _is_promotable_filename(normalized_path: str) -> bool:
    return not any(pattern.search(normalized_path) for pattern in _SKIP_PROMOTION_PATTERNS)


@router.post("", response_model=SourceRootPublic, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: CreateSourceRequest,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> SourceRootPublic:
    knowledge_space = (
        await db.execute(
            select(KnowledgeSpace).where(
                KnowledgeSpace.id == payload.knowledge_space_id,
                KnowledgeSpace.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if knowledge_space is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge space not found"
        )

    source = SourceRoot(
        organization_id=membership.organization_id,
        knowledge_space_id=payload.knowledge_space_id,
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


@router.post("/{source_id}/disable", response_model=SourceRootPublic)
async def disable_source(
    source_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> SourceRootPublic:
    """LAN-M6 gap: the mitigation for a misconfigured source was previously
    just "stop clicking scan/promote" — this makes it an actual, enforced
    stop rather than an operator convention. Never deletes the source or its
    already-promoted documents; see docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md.
    """
    source = await _get_org_scoped_source(db, source_id, membership.organization_id)
    source.is_enabled = False
    await db.commit()
    await db.refresh(source)
    return SourceRootPublic.model_validate(source, from_attributes=True)


@router.post("/{source_id}/enable", response_model=SourceRootPublic)
async def enable_source(
    source_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> SourceRootPublic:
    source = await _get_org_scoped_source(db, source_id, membership.organization_id)
    source.is_enabled = True
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
    if not source.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source is disabled — re-enable it before triggering a scan.",
        )

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
    entries = result.scalars().all()

    promotion_status_by_entry: dict[uuid.UUID, PromotionStatus] = {}
    if entries:
        promotion_rows = await db.execute(
            select(PromotionRecord.source_entry_id, PromotionRecord.status).where(
                PromotionRecord.source_entry_id.in_([e.id for e in entries])
            )
        )
        promotion_status_by_entry = dict(promotion_rows.all())

    return [
        SourceEntryPublic(
            id=entry.id,
            normalized_path=entry.normalized_path,
            size_bytes=entry.size_bytes,
            mtime=entry.mtime,
            discovery_status=entry.discovery_status,
            access_status=entry.access_status,
            promotion_status=promotion_status_by_entry.get(entry.id),
            updated_at=entry.updated_at,
        )
        for entry in entries
    ]


@router.post(
    "/{source_id}/entries/promote",
    response_model=PromoteEntriesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def promote_entries(
    source_id: uuid.UUID,
    payload: PromoteEntriesRequest,
    membership: OrganizationMember = Depends(require_role(*_MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> PromoteEntriesResponse:
    """Queues selected catalog entries for promotion into the existing
    document pipeline (LAN-M2). Idempotent: an entry that already has an
    active PromotionRecord is skipped, not duplicated — re-requesting
    promotion of the same entries is always safe.
    """
    source = await _get_org_scoped_source(db, source_id, membership.organization_id)
    if not source.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source is disabled — re-enable it before promoting entries.",
        )

    entries = (
        await db.execute(
            select(SourceEntry).where(
                SourceEntry.id.in_(payload.source_entry_ids),
                SourceEntry.source_root_id == source_id,
            )
        )
    ).scalars().all()
    entry_by_id = {e.id: e for e in entries}

    already_promoted = {
        row[0]
        for row in (
            await db.execute(
                select(PromotionRecord.source_entry_id).where(
                    PromotionRecord.source_entry_id.in_(payload.source_entry_ids)
                )
            )
        ).all()
    }

    created: list[PromotionRecord] = []
    for entry_id in payload.source_entry_ids:
        entry = entry_by_id.get(entry_id)
        if entry is None or entry_id in already_promoted:
            continue
        if not _is_promotable_filename(entry.normalized_path):
            continue
        record = PromotionRecord(
            organization_id=membership.organization_id,
            source_entry_id=entry_id,
            status=PromotionStatus.QUEUED,
        )
        db.add(record)
        created.append(record)

    if created:
        await db.commit()
        for record in created:
            await db.refresh(record)
            enqueue_promote_source_entry(str(record.id))

    return PromoteEntriesResponse(
        created=[
            PromotionRecordPublic.model_validate(record, from_attributes=True)
            for record in created
        ]
    )
