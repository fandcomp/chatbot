"""Hierarchical chunk model (M5, master spec $22-26).

Chunks are built from M4's already-approved canonical tree — this module
never re-interprets structure, it only groups/splits already-typed
`document_nodes` text into retrieval units. Embedding/Qdrant/sparse index
are M6; `semantic_summary` is schema-provisioned here but stays NULL until a
later milestone populates it (no LLM gateway exists yet).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_nodes.id"), nullable=False
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    previous_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    next_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # Immutable evidence/citation source (addendum $24.1) — never rewritten
    # once created.
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Document/BAB/Pasal/Ayat-prefixed representation for embedding (addendum
    # $24.2), rendered generically from the anchor node's own
    # structural_path_json so a non-legal grammar never gets a fabricated
    # "Pasal:" label.
    contextual_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional retrieval-enrichment summary (addendum $24.3) — never used as
    # evidence. Unpopulated until an LLM gateway exists (M9+).
    semantic_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    structural_path_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
