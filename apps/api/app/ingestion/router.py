import hashlib
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_action
from app.auth.dependencies import get_current_membership, require_role
from app.auth.router import limiter
from app.core.config import settings
from app.core.database import get_db
from app.core.storage import build_original_object_key, put_object
from app.core.tasks import enqueue_verify_upload
from app.documents.models import Document, DocumentLifecycleStatus, DocumentVersion
from app.ingestion.models import ProcessingJob, ProcessingJobStatus
from app.ingestion.schemas import ProcessingJobPublic, UploadResponse
from app.ingestion.validation import (
    UploadValidationError,
    mime_type_for_extension,
    sanitize_filename,
    validate_extension,
    validate_magic_bytes,
    validate_size,
)
from app.knowledge.models import KnowledgeSpace
from app.organizations.models import OrganizationMember, OrgRole

router = APIRouter(tags=["ingestion"])


@router.post(
    "/documents/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("20/minute")
async def upload_document(
    request: Request,
    file: UploadFile,
    knowledge_space_id: uuid.UUID = Form(...),
    membership: OrganizationMember = Depends(
        require_role(OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    space_result = await db.execute(
        select(KnowledgeSpace).where(
            KnowledgeSpace.id == knowledge_space_id,
            KnowledgeSpace.organization_id == membership.organization_id,
        )
    )
    if space_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge space not found")

    filename = file.filename or "upload"
    try:
        extension = validate_extension(filename)
        content = await file.read()
        validate_size(content, settings.MAX_FILE_SIZE_MB)
        validate_magic_bytes(extension, content)
    except UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    file_hash = hashlib.sha256(content).hexdigest()

    duplicate_result = await db.execute(
        select(DocumentVersion.document_id).where(
            DocumentVersion.organization_id == membership.organization_id,
            DocumentVersion.file_hash == file_hash,
        )
    )
    duplicate_document_id = duplicate_result.scalar_one_or_none()
    if duplicate_document_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate document — identical content already exists as document {duplicate_document_id}.",
        )

    sanitized_filename = sanitize_filename(filename)
    title = sanitized_filename.rsplit(".", 1)[0] or sanitized_filename

    document = Document(
        organization_id=membership.organization_id,
        knowledge_space_id=knowledge_space_id,
        title=title,
    )
    db.add(document)
    await db.flush()

    version = DocumentVersion(
        organization_id=membership.organization_id,
        document_id=document.id,
        version_number=1,
        file_hash=file_hash,
        original_filename=sanitized_filename,
        mime_type=mime_type_for_extension(extension),
        size_bytes=len(content),
        storage_path="",
        status=DocumentLifecycleStatus.UPLOADED,
    )
    db.add(version)
    await db.flush()

    storage_key = build_original_object_key(
        membership.organization_id, document.id, version.id, sanitized_filename
    )
    version.storage_path = storage_key

    job = ProcessingJob(
        organization_id=membership.organization_id,
        document_version_id=version.id,
        status=ProcessingJobStatus.QUEUED,
    )
    db.add(job)
    await db.flush()

    # Write to S3 before committing: if this raises, the transaction never
    # commits and no orphaned DB rows are left pointing at a missing object.
    put_object(storage_key, content, mime_type_for_extension(extension))

    job.celery_task_id = enqueue_verify_upload(str(job.id))

    await log_action(
        db,
        actor_id=membership.user_id,
        organization_id=membership.organization_id,
        action="document_upload",
        entity_type="document",
        entity_id=document.id,
        new_value={"filename": sanitized_filename, "file_hash": file_hash},
    )
    await db.commit()

    return UploadResponse(
        document_id=document.id,
        document_version_id=version.id,
        processing_job_id=job.id,
        status=version.status,
    )


@router.get("/processing-jobs/{job_id}", response_model=ProcessingJobPublic)
async def get_processing_job(
    job_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJobPublic:
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.organization_id == membership.organization_id
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Processing job not found")
    return ProcessingJobPublic.model_validate(job)
