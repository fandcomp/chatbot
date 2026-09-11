"""Shared direct-DB seeding helpers for M7 retrieval integration tests.

Mirrors workers/document_worker/tests/test_index_document.py's convention of
inserting document_regions/document_nodes/document_chunks rows directly
rather than running the real Docling/chunking/indexing pipeline end to end —
apps/api has no synchronous way to drive a document to ACTIVE in a test.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.models import DocumentChunk
from app.documents.models import Document, DocumentLifecycleStatus, DocumentVersion
from app.knowledge.models import KnowledgeSpace
from app.parsing.models import (
    DocumentNode,
    DocumentNodeType,
    DocumentRegion,
    StructuralRegionType,
)
from app.sources.models import SourceEntry, SourceRoot, SourceType


async def resolve_organization_id(db: AsyncSession, knowledge_space_id: uuid.UUID) -> uuid.UUID:
    return (
        await db.execute(
            select(KnowledgeSpace.organization_id).where(KnowledgeSpace.id == knowledge_space_id)
        )
    ).scalar_one()


async def seed_lan_source_entry(
    db: AsyncSession, organization_id: uuid.UUID, knowledge_space_id: uuid.UUID
) -> uuid.UUID:
    """LAN-M4: a minimal SourceRoot/SourceEntry pair, just enough to attach a
    DocumentVersion.source_entry_id — proves retrieval/revocation treats a
    LAN-promoted document identically to an uploaded one, with no
    source-type branching anywhere downstream (there is none to test).
    """
    root = SourceRoot(
        organization_id=organization_id,
        knowledge_space_id=knowledge_space_id,
        source_type=SourceType.LOCAL_FAKE,
        display_name="Retrieval isolation test root",
        root_path="/tmp/retrieval-isolation-test",
    )
    db.add(root)
    await db.flush()

    entry = SourceEntry(
        organization_id=organization_id,
        source_root_id=root.id,
        normalized_path="test.pdf",
        size_bytes=100,
    )
    db.add(entry)
    await db.flush()

    return entry.id


async def seed_active_document(
    db: AsyncSession,
    organization_id: uuid.UUID,
    knowledge_space_id: uuid.UUID,
    title: str = "Test Regulation",
    status: DocumentLifecycleStatus = DocumentLifecycleStatus.ACTIVE,
    source_entry_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Creates Document + DocumentVersion(status) + one DocumentRegion.

    `source_entry_id` (LAN-M4) marks the version as LAN-promoted, same as
    the real promote_source_entry task does — every retrieval/revocation
    path must treat it identically to a NULL (ordinary upload) version.

    Returns (document_id, version_id, region_id).
    """
    document = Document(
        organization_id=organization_id, knowledge_space_id=knowledge_space_id, title=title
    )
    db.add(document)
    await db.flush()

    version = DocumentVersion(
        organization_id=organization_id,
        document_id=document.id,
        version_number=1,
        file_hash=uuid.uuid4().hex,
        original_filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        storage_path="unused/path.pdf",
        status=status,
        source_entry_id=source_entry_id,
    )
    db.add(version)
    await db.flush()

    region = DocumentRegion(
        organization_id=organization_id,
        document_version_id=version.id,
        region_type=StructuralRegionType.LEGAL_BODY,
        page_start=1,
        page_end=5,
        sequence_number=0,
        confidence=0.95,
    )
    db.add(region)
    await db.flush()

    return document.id, version.id, region.id


async def seed_node_and_chunk(
    db: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    region_id: uuid.UUID,
    *,
    node_type: DocumentNodeType,
    sequence_number: int,
    original_text: str,
    structural_path_json: list[dict],
    structural_path_text: str | None = None,
    structural_depth: int = 1,
    article_number: str | None = None,
    clause_number: str | None = None,
    letter_number: str | None = None,
    appendix_number: str | None = None,
    chapter_number: str | None = None,
    number_raw: str | None = None,
    number_normalized: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    node = DocumentNode(
        organization_id=organization_id,
        document_version_id=version_id,
        region_id=region_id,
        node_type=node_type,
        number_raw=number_raw,
        number_normalized=number_normalized,
        depth=structural_depth - 1,
        sequence_number=sequence_number,
        page_start=1,
        page_end=1,
        confidence=0.95,
        source_provenance={},
        structural_path_json=structural_path_json,
        structural_path_text=structural_path_text,
        structural_depth=structural_depth,
        chapter_number=chapter_number,
        article_number=article_number,
        clause_number=clause_number,
        letter_number=letter_number,
        appendix_number=appendix_number,
    )
    db.add(node)
    await db.flush()

    chunk = DocumentChunk(
        organization_id=organization_id,
        document_id=document_id,
        document_version_id=version_id,
        source_node_id=node.id,
        depth=0,
        sequence_number=sequence_number,
        page_start=1,
        page_end=1,
        original_text=original_text,
        contextual_text=original_text,
        token_count=max(len(original_text.split()), 1),
        structural_path_text=structural_path_text,
    )
    db.add(chunk)
    await db.flush()

    return node.id, chunk.id
