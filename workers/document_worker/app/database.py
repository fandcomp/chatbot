"""Minimal DB access for this worker.

This process is a separate `uv` project from apps/api and does not import its
ORM models. It defines Core `Table` objects for just the columns it actually
touches (document_versions.status/file_hash/storage_path/organization_id,
processing_jobs.status/attempts/error_message, and — as of M3 —
document_regions/document_nodes in full, since the worker is the sole writer
of those tables). These must be kept in sync by hand with
apps/api/app/documents/models.py, apps/api/app/ingestion/models.py, and
apps/api/app/parsing/models.py if those columns ever change — the same
cross-process drift risk ADR-016 already flags for the producer/consumer
split.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table, Text
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
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
    Column("original_filename", String(255)),
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

# M3: this worker is the sole writer of document_regions/document_nodes, so
# these mirror apps/api/app/parsing/models.py's full column set (not a
# touched-columns-only subset like the tables above).
_structural_region_type = ENUM(
    "COVER",
    "TABLE_OF_CONTENTS",
    "LEGAL_PREAMBLE",
    "LEGAL_BODY",
    "LEGAL_DECISION",
    "TECHNICAL_GUIDELINE",
    "PROCEDURAL_GUIDELINE",
    "NUMBERED_MANUAL",
    "SOP",
    "APPENDIX",
    "TABLE_REGION",
    "DIAGRAM_REGION",
    "ORGANIZATION_CHART",
    "FLOWCHART",
    "EMBEDDED_TEMPLATE",
    "ACADEMIC_TEMPLATE",
    "FREEFORM_SECTION",
    "UNKNOWN",
    name="structural_region_type",
    create_type=False,
)
_document_node_type = ENUM(
    "DOCUMENT",
    "REGION",
    "TITLE",
    "SUBTITLE",
    "CHAPTER",
    "PART",
    "SECTION",
    "SUBSECTION",
    "NUMBERED_SECTION",
    "NUMBERED_ITEM",
    "LETTER_ITEM",
    "ROMAN_ITEM",
    "NESTED_ITEM",
    "ARTICLE",
    "CLAUSE",
    "DECISION_ITEM",
    "PARAGRAPH",
    "LIST",
    "LIST_ITEM",
    "TABLE",
    "TABLE_ROW",
    "TABLE_CELL",
    "APPENDIX",
    "FIGURE",
    "DIAGRAM",
    "FLOWCHART",
    "ORGANIZATION_CHART",
    "FOOTNOTE",
    "SIGNATURE_BLOCK",
    "UNKNOWN_BLOCK",
    name="document_node_type",
    create_type=False,
)
_numbering_style = ENUM(
    "DECIMAL_DOT",
    "DECIMAL_PAREN_CLOSE",
    "DECIMAL_PAREN_FULL",
    "LETTER_DOT",
    "LETTER_PAREN_CLOSE",
    "LETTER_PAREN_FULL",
    "ROMAN_UPPER_DOT",
    "ROMAN_LOWER_DOT",
    "LETTER_UPPER_DOT",
    "ORDINAL_WORD",
    "UNKNOWN",
    name="numbering_style",
    create_type=False,
)

document_regions = Table(
    "document_regions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("region_type", _structural_region_type),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("sequence_number", Integer),
    Column("confidence", Numeric(4, 3)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

document_nodes = Table(
    "document_nodes",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("region_id", UUID(as_uuid=True)),
    Column("parent_id", UUID(as_uuid=True)),
    Column("previous_id", UUID(as_uuid=True)),
    Column("next_id", UUID(as_uuid=True)),
    Column("node_type", _document_node_type),
    # semantic_role intentionally omitted — unused (NULL) until M4, no reason
    # for this worker to write it.
    Column("label", String(255)),
    Column("title", String(1024)),
    Column("number_raw", String(64)),
    Column("number_normalized", String(64)),
    Column("numbering_style", _numbering_style),
    Column("text", Text),
    Column("normalized_text", Text),
    Column("depth", Integer),
    Column("sequence_number", Integer),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("bounding_box", JSONB),
    Column("confidence", Numeric(4, 3)),
    Column("source_provenance", JSONB),
    Column("structural_path_json", JSONB),
    Column("structural_depth", Integer),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
