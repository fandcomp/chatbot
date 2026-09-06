import uuid
from datetime import datetime

from pydantic import BaseModel

from app.documents.models import DocumentLifecycleStatus


class DocumentPublic(BaseModel):
    id: uuid.UUID
    title: str
    knowledge_space_id: uuid.UUID
    latest_version_id: uuid.UUID
    latest_version_status: DocumentLifecycleStatus
    latest_processing_job_id: uuid.UUID | None
    created_at: datetime


class ArchiveResult(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    status: DocumentLifecycleStatus
