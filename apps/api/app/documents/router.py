import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.caching.answer_cache import AnswerCacheService
from app.chunking.models import DocumentChunk
from app.core.database import get_db
from app.core.storage import delete_object
from app.documents.models import (
    Document,
    DocumentLifecycleStatus,
    DocumentRelation,
    DocumentRelationType,
    DocumentVersion,
)
from app.documents.schemas import (
    ArchiveResult,
    CreateRelationRequest,
    DocumentPublic,
    DocumentRelationPublic,
    RollbackResult,
)
from app.indexing.qdrant_client import delete_document_points
from app.ingestion.models import ProcessingJob
from app.organizations.models import OrganizationMember, OrgRole
from app.parsing.models import DocumentNode, DocumentRegion

router = APIRouter(prefix="/documents", tags=["documents"])


async def latest_version(db: AsyncSession, document_id: uuid.UUID) -> DocumentVersion:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one()


async def latest_active_version(db: AsyncSession, document_id: uuid.UUID) -> DocumentVersion | None:
    """Like `latest_version`, but only a version that has actually cleared
    approval (spec §9's ACTIVE) counts — used wherever a document is about to
    be cited as the SOURCE of a claim about another document (e.g. "this
    AMENDS that"), so an unapproved document's title/relation can never reach
    another document's citations before it has been through admin review.
    """
    result = await db.execute(
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.status == DocumentLifecycleStatus.ACTIVE,
        )
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_job_id(db: AsyncSession, document_version_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(ProcessingJob.id)
        .where(ProcessingJob.document_version_id == document_version_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _to_document_public(db: AsyncSession, document: Document) -> DocumentPublic:
    version = await latest_version(db, document.id)
    job_id = await _latest_job_id(db, version.id)
    return DocumentPublic(
        id=document.id,
        title=document.title,
        knowledge_space_id=document.knowledge_space_id,
        latest_version_id=version.id,
        latest_version_status=version.status,
        latest_processing_job_id=job_id,
        created_at=document.created_at,
    )


async def get_org_scoped_document(
    db: AsyncSession, document_id: uuid.UUID, organization_id: uuid.UUID
) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.organization_id == organization_id
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.get("", response_model=list[DocumentPublic])
async def list_documents(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentPublic]:
    result = await db.execute(
        select(Document).where(Document.organization_id == membership.organization_id)
    )
    documents = result.scalars().all()
    return [await _to_document_public(db, document) for document in documents]


@router.get("/{document_id}", response_model=DocumentPublic)
async def get_document(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> DocumentPublic:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)
    return await _to_document_public(db, document)


@router.post("/{document_id}/archive", response_model=ArchiveResult)
async def archive_document(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ArchiveResult:
    """spec §9: ACTIVE -> ARCHIVED. Correctness needs no Qdrant cleanup — M7's
    retrieval already re-verifies status live against Postgres on every
    query, so a stale Qdrant point for this version is excluded there
    regardless (same reasoning as the worker's auto-supersede logic, M13).
    """
    document = await get_org_scoped_document(db, document_id, membership.organization_id)
    version = await latest_version(db, document.id)

    if version.status != DocumentLifecycleStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an ACTIVE document can be archived.",
        )

    version.status = DocumentLifecycleStatus.ARCHIVED
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_archive",
        entity_type="document_version",
        entity_id=version.id,
    )
    await db.commit()
    await db.refresh(version)
    # spec §45: cached answers must be invalidated when a document's status
    # changes — an archived source should never keep serving a cached
    # answer that cited it as ACTIVE.
    await AnswerCacheService().invalidate_organization(membership.organization_id)

    return ArchiveResult(document_id=document.id, document_version_id=version.id, status=version.status)


@router.post("/{document_id}/versions/{version_id}/rollback", response_model=RollbackResult)
async def rollback_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> RollbackResult:
    """M13's "rollback design" target — restores a previously-ACTIVE version
    (SUPERSEDED by a later version, or ARCHIVED by an admin) back to ACTIVE.
    The complement of `archive_document`/the worker's auto-supersede: both of
    those only ever move a version forward, out of ACTIVE; this is the one
    path back in.

    Correctness needs no Qdrant cleanup or re-indexing, same reasoning as
    archive_document: a version only ever reaches SUPERSEDED/ARCHIVED after
    having been ACTIVE, which means it was indexed with
    `document_status=ACTIVE` baked into its Qdrant payload at the time — M7's
    retrieval already re-verifies status live against Postgres on every
    query, so flipping the Postgres status back to ACTIVE is sufficient on
    its own.
    """
    document = await get_org_scoped_document(db, document_id, membership.organization_id)

    target = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id, DocumentVersion.document_id == document.id
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document version not found")

    if target.status not in (DocumentLifecycleStatus.SUPERSEDED, DocumentLifecycleStatus.ARCHIVED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a SUPERSEDED or ARCHIVED version can be rolled back to.",
        )

    current_active = await latest_active_version(db, document.id)
    superseded_version_id: uuid.UUID | None = None
    if current_active is not None:
        current_active.status = DocumentLifecycleStatus.SUPERSEDED
        db.add(
            DocumentRelation(
                organization_id=membership.organization_id,
                from_document_version_id=current_active.id,
                to_document_version_id=target.id,
                relation_type=DocumentRelationType.SUPERSEDED_BY,
            )
        )
        superseded_version_id = current_active.id

    target.status = DocumentLifecycleStatus.ACTIVE
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_version_rollback",
        entity_type="document_version",
        entity_id=target.id,
        old_value={"superseded_version_id": str(superseded_version_id)} if superseded_version_id else None,
    )
    await db.commit()
    await db.refresh(target)
    # spec §45: cached answers must be invalidated when a document's status
    # changes — a rolled-back-to version should serve fresh evidence, not a
    # cached answer built before it was ACTIVE again.
    await AnswerCacheService().invalidate_organization(membership.organization_id)

    return RollbackResult(
        document_id=document.id,
        document_version_id=target.id,
        status=target.status,
        superseded_version_id=superseded_version_id,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
    )
    versions = result.scalars().all()
    version_ids = [version.id for version in versions]

    # No ORM `relationship()` is declared between these models (see
    # documents/models.py, ingestion/models.py, parsing/models.py), so
    # SQLAlchemy's unit-of-work has no FK dependency graph to order these
    # deletes automatically — explicit ordering (children first, flushed
    # between stages) is required, otherwise it may attempt to delete
    # `documents` before its dependents and hit a ForeignKeyViolationError.
    if version_ids:
        # M13's auto-supersede (and any admin-curated relation, §21) creates
        # document_relations rows referencing these versions with no
        # ON DELETE CASCADE — must go before the versions themselves or this
        # would hit a ForeignKeyViolationError on any document that has ever
        # been superseded or manually related to another.
        await db.execute(
            delete(DocumentRelation).where(
                or_(
                    DocumentRelation.from_document_version_id.in_(version_ids),
                    DocumentRelation.to_document_version_id.in_(version_ids),
                )
            )
        )

        jobs_result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.document_version_id.in_(version_ids))
        )
        for job in jobs_result.scalars().all():
            await db.delete(job)

        # M5's worker may have populated document_chunks for a version that
        # reached INDEXING/ACTIVE — a chunk's source_node_id FK is NOT NULL
        # with no ON DELETE CASCADE, so chunks must go before nodes. A single
        # bulk Core DELETE sidesteps the self-referential parent_chunk_id/
        # previous_chunk_id/next_chunk_id ordering problem entirely (all
        # matching rows vanish in one statement, so no row is ever left
        # referencing an already-deleted sibling).
        await db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(version_ids))
        )

        # M3's parser (workers/document_worker) may have populated these for
        # a version that reached PARSED/REVIEW_REQUIRED — delete nodes before
        # regions (document_nodes.region_id -> document_regions.id) and
        # before the version itself.
        nodes_result = await db.execute(
            select(DocumentNode).where(DocumentNode.document_version_id.in_(version_ids))
        )
        for node in nodes_result.scalars().all():
            await db.delete(node)
        await db.flush()

        regions_result = await db.execute(
            select(DocumentRegion).where(DocumentRegion.document_version_id.in_(version_ids))
        )
        for region in regions_result.scalars().all():
            await db.delete(region)
        await db.flush()

    for version in versions:
        delete_object(version.storage_path)
        await db.delete(version)
    await db.flush()

    # M6 (ADR-002): stale Qdrant points are explicitly disallowed. Delete
    # before commit, mirroring delete_object's placement above — an
    # exception here must abort the whole transaction before anything
    # commits, the same failure semantics the S3 delete already has.
    await delete_document_points(membership.organization_id, document_id)

    await db.delete(document)
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_delete",
        entity_type="document",
        entity_id=document_id,
    )
    await db.commit()
    # spec §57: deleting a document must also clear "cached answers".
    await AnswerCacheService().invalidate_organization(membership.organization_id)


def _relation_public(
    relation: DocumentRelation,
    from_document_id: uuid.UUID,
    from_document_title: str,
    to_document_id: uuid.UUID,
    to_document_title: str,
) -> DocumentRelationPublic:
    return DocumentRelationPublic(
        id=relation.id,
        from_document_id=from_document_id,
        from_document_title=from_document_title,
        to_document_id=to_document_id,
        to_document_title=to_document_title,
        relation_type=relation.relation_type,
        created_at=relation.created_at,
    )


@router.post(
    "/{document_id}/relations",
    response_model=DocumentRelationPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_relation(
    document_id: uuid.UUID,
    payload: CreateRelationRequest,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> DocumentRelationPublic:
    """spec §21: admin-curated relations between two documents (e.g. "Regulation
    B AMENDS Regulation A") — surfaced later as a citation warning by
    AdaptiveCitationService so a user citing Regulation A learns it has been
    amended, even though Regulation A's own version is still ACTIVE.
    """
    if payload.relation_type == DocumentRelationType.SUPERSEDED_BY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SUPERSEDED_BY is only ever set automatically when a document version "
            "reaches ACTIVE; it cannot be created directly.",
        )
    if payload.target_document_id == document_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="A document cannot relate to itself."
        )

    from_document = await get_org_scoped_document(db, document_id, membership.organization_id)
    to_document = await get_org_scoped_document(
        db, payload.target_document_id, membership.organization_id
    )
    from_version = await latest_active_version(db, from_document.id)
    if from_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an ACTIVE document version can be cited as the source of a "
            "relation — this document has not been approved and published yet.",
        )
    to_version = await latest_version(db, to_document.id)

    relation = DocumentRelation(
        organization_id=membership.organization_id,
        from_document_version_id=from_version.id,
        to_document_version_id=to_version.id,
        relation_type=payload.relation_type,
    )
    db.add(relation)
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_relation_create",
        entity_type="document_relation",
        entity_id=relation.id,
        new_value={
            "from_document_id": str(from_document.id),
            "to_document_id": str(to_document.id),
            "relation_type": payload.relation_type.value,
        },
    )
    await db.commit()
    await db.refresh(relation)
    # A cached answer citing either document was built before this relation
    # existed — it must not keep serving a citation missing this warning.
    await AnswerCacheService().invalidate_organization(membership.organization_id)

    return _relation_public(relation, from_document.id, from_document.title, to_document.id, to_document.title)


@router.get("/{document_id}/relations", response_model=list[DocumentRelationPublic])
async def list_relations(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentRelationPublic]:
    document = await get_org_scoped_document(db, document_id, membership.organization_id)

    from_version = aliased(DocumentVersion)
    to_version = aliased(DocumentVersion)
    from_doc = aliased(Document)
    to_doc = aliased(Document)

    rows = (
        await db.execute(
            select(DocumentRelation, from_doc, to_doc)
            .join(from_version, DocumentRelation.from_document_version_id == from_version.id)
            .join(to_version, DocumentRelation.to_document_version_id == to_version.id)
            .join(from_doc, from_version.document_id == from_doc.id)
            .join(to_doc, to_version.document_id == to_doc.id)
            .where(
                DocumentRelation.organization_id == membership.organization_id,
                or_(from_doc.id == document.id, to_doc.id == document.id),
            )
        )
    ).all()
    return [
        _relation_public(relation, from_doc_row.id, from_doc_row.title, to_doc_row.id, to_doc_row.title)
        for relation, from_doc_row, to_doc_row in rows
    ]


@router.delete("/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_relation(
    relation_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(DocumentRelation).where(
            DocumentRelation.id == relation_id,
            DocumentRelation.organization_id == membership.organization_id,
        )
    )
    relation = result.scalar_one_or_none()
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relation not found")
    if relation.relation_type == DocumentRelationType.SUPERSEDED_BY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SUPERSEDED_BY reflects the worker's own version history and cannot be "
            "deleted directly.",
        )

    await db.delete(relation)
    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_relation_delete",
        entity_type="document_relation",
        entity_id=relation_id,
    )
    await db.commit()
    await AnswerCacheService().invalidate_organization(membership.organization_id)
