import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.sources.models import (
    DiscoveryStatus,
    EntryAccessStatus,
    ScanRunStatus,
    SourceHealth,
    SourceType,
)


class CreateSourceRequest(BaseModel):
    source_type: SourceType
    display_name: str = Field(min_length=1, max_length=255)
    root_path: str = Field(min_length=1, max_length=1024)
    allowed_subtrees: list[str] | None = None
    credential_reference: str | None = None


class SourceRootPublic(BaseModel):
    id: uuid.UUID
    source_type: SourceType
    display_name: str
    root_path: str
    allowed_subtrees: list[str] | None
    health: SourceHealth
    health_checked_at: datetime | None
    created_at: datetime


class ScanRunPublic(BaseModel):
    id: uuid.UUID
    source_root_id: uuid.UUID
    status: ScanRunStatus
    entries_seen: int
    entries_new: int
    entries_updated: int
    error_summary: list[dict] | None
    started_at: datetime
    finished_at: datetime | None


class TriggerScanResponse(BaseModel):
    scan_run_id: uuid.UUID
    status: ScanRunStatus


class SourceEntryPublic(BaseModel):
    id: uuid.UUID
    normalized_path: str
    size_bytes: int
    mtime: datetime | None
    discovery_status: DiscoveryStatus
    access_status: EntryAccessStatus
    updated_at: datetime
