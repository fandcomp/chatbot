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

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
)
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
    # M5: chunk_document needs this to populate document_chunks.document_id
    # and to join documents.title for contextual_text's "Dokumen:" line.
    Column("document_id", UUID(as_uuid=True)),
    Column("file_hash", String(64)),
    Column("original_filename", String(255)),
    # LAN-M2: needed to INSERT a version (the worker now creates these
    # itself for a promoted LAN file, not just read/update them).
    Column("mime_type", String(100)),
    Column("size_bytes", Integer),
    Column("source_entry_id", UUID(as_uuid=True)),
    Column("storage_path", String(1024)),
    Column("status", _document_lifecycle_status),
    # M6: index_document's Qdrant payload includes the source version number.
    Column("version_number", Integer),
    Column("updated_at", DateTime(timezone=True)),
)

# M5/M6: title (contextual_text rendering) + knowledge_space_id (M6 payload
# field). LAN-M2 adds organization_id since the worker now INSERTs a new
# Document row itself for a promoted LAN file (previously read-only here).
documents = Table(
    "documents",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("title", String(255)),
    Column("knowledge_space_id", UUID(as_uuid=True)),
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
# M4: SpecializedStructureInterpreter is the first writer of semantic_role.
_semantic_role = ENUM(
    "GENERAL",
    "PURPOSE",
    "OBJECTIVE",
    "SCOPE",
    "LEGAL_BASIS",
    "DEFINITION",
    "POSITION",
    "PRINCIPLE",
    "PLANNING",
    "PREPARATION",
    "EXECUTION",
    "TERMINATION",
    "PROCEDURE",
    "REQUIREMENT",
    "RESPONSIBILITY",
    "AUTHORITY",
    "DUTY",
    "PROHIBITION",
    "COMMAND",
    "CONTROL",
    "DECISION",
    "VALIDITY",
    "ORGANIZATION_STRUCTURE",
    "PROCESS_FLOW",
    "CONCLUSION",
    "RECOMMENDATION",
    "UNKNOWN",
    name="semantic_role",
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
    Column("semantic_role", _semantic_role),
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
    Column("structural_path_text", Text),
    Column("structural_depth", Integer),
    Column("visual_source_type", String(64)),
    Column("chapter_number", String(64)),
    Column("article_number", String(64)),
    Column("clause_number", String(64)),
    Column("letter_number", String(64)),
    Column("appendix_number", String(64)),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

document_structure_profiles = Table(
    "document_structure_profiles",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("contains_articles", Boolean),
    Column("contains_numbered_sections", Boolean),
    Column("contains_chapters", Boolean),
    Column("contains_decision_preamble", Boolean),
    Column("contains_appendices", Boolean),
    Column("contains_tables", Boolean),
    Column("contains_diagrams", Boolean),
    Column("contains_embedded_document", Boolean),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

# M5: this worker is the sole writer of document_chunks, mirroring the
# document_regions/document_nodes pattern above.
document_chunks = Table(
    "document_chunks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("document_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("source_node_id", UUID(as_uuid=True)),
    Column("parent_chunk_id", UUID(as_uuid=True)),
    Column("previous_chunk_id", UUID(as_uuid=True)),
    Column("next_chunk_id", UUID(as_uuid=True)),
    Column("depth", Integer),
    Column("sequence_number", Integer),
    Column("page_start", Integer),
    Column("page_end", Integer),
    Column("original_text", Text),
    Column("contextual_text", Text),
    Column("semantic_summary", Text),
    Column("token_count", Integer),
    Column("structural_path_text", Text),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

_document_relation_type = ENUM(
    "AMENDS",
    "REPEALS",
    "REPLACES",
    "IMPLEMENTS",
    "REFERS_TO",
    "SUPERSEDED_BY",
    name="document_relation_type",
    create_type=False,
)

# M13: index_document is the sole writer of the auto-generated SUPERSEDED_BY
# relation (spec §21) — created the moment a new version reaches ACTIVE and
# the document's previous ACTIVE version is flipped to SUPERSEDED.
document_relations = Table(
    "document_relations",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("from_document_version_id", UUID(as_uuid=True)),
    Column("to_document_version_id", UUID(as_uuid=True)),
    Column("relation_type", _document_relation_type),
    Column("created_at", DateTime(timezone=True)),
)


_lan_source_type = ENUM("LOCAL_FAKE", "WINDOWS_UNC", name="lan_source_type", create_type=False)
_lan_source_health = ENUM(
    "HEALTHY", "UNREACHABLE", "ACCESS_DENIED", "PARTIAL", "UNKNOWN",
    name="lan_source_health", create_type=False,
)
_lan_scan_run_status = ENUM(
    "RUNNING", "COMPLETED", "PARTIAL", "FAILED", name="lan_scan_run_status", create_type=False
)
_lan_discovery_status = ENUM(
    "PRESENT", "MISSING_CANDIDATE", "CONFIRMED_MISSING",
    name="lan_discovery_status", create_type=False,
)
_lan_entry_access_status = ENUM(
    "OK", "ACCESS_DENIED", "NETWORK_ERROR", "NOT_FOUND",
    name="lan_entry_access_status", create_type=False,
)
_lan_promotion_status = ENUM(
    "QUEUED", "STABILITY_WAIT", "STAGING", "DUPLICATE_LINKED", "COMPLETED",
    "FAILED", "PAUSED_CAPACITY", name="lan_promotion_status", create_type=False,
)

# LAN-M1 (ADR-020) — apps/api creates source_roots and owns source_type/
# root_path/allowed_subtrees/knowledge_space_id; this worker reads those to
# pick/configure an adapter and know where a promotion lands, and is the
# sole writer of health/health_checked_at.
source_roots = Table(
    "source_roots",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("knowledge_space_id", UUID(as_uuid=True)),
    Column("source_type", _lan_source_type),
    Column("root_path", String(1024)),
    Column("allowed_subtrees", JSONB),
    Column("health", _lan_source_health),
    Column("health_checked_at", DateTime(timezone=True)),
)

scan_runs = Table(
    "scan_runs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("source_root_id", UUID(as_uuid=True)),
    Column("status", _lan_scan_run_status),
    Column("cursor", JSONB),
    Column("entries_seen", Integer),
    Column("entries_new", Integer),
    Column("entries_updated", Integer),
    Column("error_summary", JSONB),
    Column("finished_at", DateTime(timezone=True)),
)

source_entries = Table(
    "source_entries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("source_root_id", UUID(as_uuid=True)),
    Column("normalized_path", String(2048)),
    Column("size_bytes", Integer),
    Column("mtime", DateTime(timezone=True)),
    Column("last_seen_scan_id", UUID(as_uuid=True)),
    Column("discovery_status", _lan_discovery_status),
    Column("access_status", _lan_entry_access_status),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

# LAN-M2 — this worker is the sole writer end-to-end (apps/api only creates
# the initial QUEUED row and reads status back for the entries list).
promotion_records = Table(
    "promotion_records",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("organization_id", UUID(as_uuid=True)),
    Column("source_entry_id", UUID(as_uuid=True)),
    Column("document_id", UUID(as_uuid=True)),
    Column("document_version_id", UUID(as_uuid=True)),
    Column("status", _lan_promotion_status),
    Column("lease_owner", UUID(as_uuid=True)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("attempts", Integer),
    Column("error_message", String(2048)),
    Column("updated_at", DateTime(timezone=True)),
)


# ADR-019: interpret_document (app/tasks.py) is the sole writer of this
# worker's audit entries — one row per confidence-based auto-approval, so
# there is always a durable record of which system decision skipped the
# manual admin approve step. Mirrors apps/api/app/audit/models.py's
# AuditLog; actor_id is left NULL here since the actor is the system, not a
# user.
audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("actor_id", UUID(as_uuid=True)),
    Column("organization_id", UUID(as_uuid=True)),
    Column("action", String(100)),
    Column("entity_type", String(100)),
    Column("entity_id", UUID(as_uuid=True)),
    Column("old_value", JSONB),
    Column("new_value", JSONB),
    Column("created_at", DateTime(timezone=True)),
)


# LAN-M3 (addendum §5): closes the "no embedding cache" gap — global, not
# tenant-scoped, since an embedding only ever depends on contextual_text +
# embedding config, never on which tenant/document it came from. Mirrors
# apps/api/app/indexing/models.py::EmbeddingCacheEntry.
embedding_cache_entries = Table(
    "embedding_cache_entries",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("cache_key", String(64)),
    Column("model", String(255)),
    Column("revision", String(255)),
    Column("dimension", Integer),
    Column("normalized", Boolean),
    Column("embedding", ARRAY(Float)),
    Column("created_at", DateTime(timezone=True)),
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
