"""Minimal DB access for this worker.

This process is a separate `uv` project from apps/api and does not import its
ORM models. It defines Core `Table` objects for just the columns it actually
touches (document_versions.status/file_hash/storage_path/organization_id,
processing_jobs.status/attempts/error_message). These must be kept in sync by
hand with apps/api/app/documents/models.py and apps/api/app/ingestion/models.py
if those columns ever change — the same cross-process drift risk ADR-016
already flags for the producer/consumer split.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# NullPool: each Celery task invocation runs its own asyncio.run() (see
# app/tasks.py), which creates and closes a fresh event loop per task. A
# pooled connection created in one task's loop is unusable once that loop
# closes — reusing it in the next task's new loop raises "Event loop is
# closed" deep inside asyncpg (confirmed live: the first task on a given
# worker process succeeds, every task after it fails this way). NullPool
# opens a fresh connection per checkout and closes it on release, so no
# connection ever outlives the loop that created it.
engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

metadata = MetaData()

# create_type=False: these Postgres enum types already exist (created by
# apps/api's Alembic migration) — this process must never try to create them.
_document_lifecycle_status = ENUM(
    "UPLOADED",
    "PROCESSING",
    "PARSED",
    "REVIEW_REQUIRED",
    "APPROVED",
    "INDEXING",
    "ACTIVE",
    "PROCESSING_FAILED",
    "SUPERSEDED",
    "ARCHIVED",
    name="document_lifecycle_status",
    create_type=False,
)
_processing_job_status = ENUM(
    "QUEUED", "PROCESSING", "SUCCEEDED", "FAILED", name="processing_job_status", create_type=False
)

document_versions = Table(
    "document_versions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("file_hash", String(64)),
    Column("storage_path", String(1024)),
    Column("status", _document_lifecycle_status),
    Column("updated_at", DateTime(timezone=True)),
)

processing_jobs = Table(
    "processing_jobs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("status", _processing_job_status),
    Column("attempts", Integer),
    Column("error_message", Text),
    Column("updated_at", DateTime(timezone=True)),
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
