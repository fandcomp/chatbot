import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.core.database import get_db
from app.core.storage import delete_object
from app.documents.models import Document, DocumentVersion
from app.documents.schemas import DocumentPublic
from app.ingestion.models import ProcessingJob
from app.organizations.models import OrganizationMember, OrgRole

router = APIRouter(prefix="/documents", tags=["documents"])


async def _latest_version(db: AsyncSession, document_id: uuid.UUID) -> DocumentVersion:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one()


async def _latest_job_id(db: AsyncSession, document_version_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(ProcessingJob.id)
        .where(ProcessingJob.document_version_id == document_version_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _to_document_public(db: AsyncSession, document: Document) -> DocumentPublic:
    version = await _latest_version(db, document.id)
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


async def _get_org_scoped_document(
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
    document = await _get_org_scoped_document(db, document_id, membership.organization_id)
    return await _to_document_public(db, document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    document = await _get_org_scoped_document(db, document_id, membership.organization_id)

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document_id)
    )
    versions = result.scalars().all()
    version_ids = [version.id for version in versions]

    # No ORM `relationship()` is declared between these models (see
    # documents/models.py, ingestion/models.py), so SQLAlchemy's unit-of-work
    # has no FK dependency graph to order these deletes automatically —
    # explicit ordering (children first, flushed between stages) is required,
    # otherwise it may attempt to delete `documents` before its dependents
    # and hit a ForeignKeyViolationError.
    if version_ids:
        jobs_result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.document_version_id.in_(version_ids))
        )
        for job in jobs_result.scalars().all():
            await db.delete(job)
        await db.flush()

    for version in versions:
        delete_object(version.storage_path)
        await db.delete(version)
    await db.flush()

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
