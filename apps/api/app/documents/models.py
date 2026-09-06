import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentLifecycleStatus(str, enum.Enum):
    """Processing/lifecycle status of a DocumentVersion (spec §9).

    Distinct from the legal/regulatory validity status (§20, ACTIVE/SUPERSEDED/
    REVOKED/DRAFT/ARCHIVED/UNKNOWN) which is not touched until M4+. M2 only ever
    sets UPLOADED, PROCESSING, PROCESSING_FAILED — the rest of the enum exists
    now so later milestones don't need an enum-alter migration.
    """

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PARSED = "PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    INDEXING = "INDEXING"
    ACTIVE = "ACTIVE"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    knowledge_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_spaces.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("organization_id", "file_hash", name="uq_document_version_org_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[DocumentLifecycleStatus] = mapped_column(
        SAEnum(DocumentLifecycleStatus, name="document_lifecycle_status"),
        nullable=False,
        default=DocumentLifecycleStatus.UPLOADED,
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentRelationType(str, enum.Enum):
    """spec §21 — relational metadata between document versions, stored in
    Postgres (never Neo4j/GraphRAG, per §101). M13's core slice only ever
    auto-creates SUPERSEDED_BY (see the worker's index_document task); the
    rest exist now so a future admin-curated-relations feature needs no
    enum-alter migration.
    """

    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    REPLACES = "REPLACES"
    IMPLEMENTS = "IMPLEMENTS"
    REFERS_TO = "REFERS_TO"
    SUPERSEDED_BY = "SUPERSEDED_BY"


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    from_document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    to_document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    relation_type: Mapped[DocumentRelationType] = mapped_column(
        SAEnum(DocumentRelationType, name="document_relation_type"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
