import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.documents.models import DocumentLifecycleStatus
from app.ingestion.models import ProcessingJobStatus


class UploadResponse(BaseModel):
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    processing_job_id: uuid.UUID
    status: DocumentLifecycleStatus


class ProcessingJobPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ProcessingJobStatus
    attempts: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
