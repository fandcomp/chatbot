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


async def resolve_organization_id(db: AsyncSession, knowledge_space_id: uuid.UUID) -> uuid.UUID:
    return (
        await db.execute(
            select(KnowledgeSpace.organization_id).where(KnowledgeSpace.id == knowledge_space_id)
        )
    ).scalar_one()


async def seed_active_document(
    db: AsyncSession,
    organization_id: uuid.UUID,
    knowledge_space_id: uuid.UUID,
    title: str = "Test Regulation",
    status: DocumentLifecycleStatus = DocumentLifecycleStatus.ACTIVE,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Creates Document + DocumentVersion(status) + one DocumentRegion.

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
