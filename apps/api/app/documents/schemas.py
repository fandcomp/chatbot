import uuid
from datetime import datetime

from pydantic import BaseModel

from app.documents.models import DocumentLifecycleStatus, DocumentRelationType


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


class CreateRelationRequest(BaseModel):
    # spec §21 — admin-curated relations (AMENDS/REPEALS/REPLACES/IMPLEMENTS/
    # REFERS_TO). SUPERSEDED_BY is excluded here: the worker auto-creates it
    # on every M13 version-supersede, and letting an admin also create one
    # by hand would let the relation graph disagree with the ACTIVE version
    # the system itself tracks.
    target_document_id: uuid.UUID
    relation_type: DocumentRelationType


class DocumentRelationPublic(BaseModel):
    id: uuid.UUID
    from_document_id: uuid.UUID
    from_document_title: str
    to_document_id: uuid.UUID
    to_document_title: str
    relation_type: DocumentRelationType
    created_at: datetime
