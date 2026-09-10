"""LAN-M1 (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §4, ADR-020) — the
source registry and discovery-scan data model. Catalog-only: nothing here
ever stores document content, and no row in this module is itself evidence
for a chat answer (that remains `documents`/`document_versions`, untouched).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SourceType(str, enum.Enum):
    """LOCAL_FAKE is the adapter every automated test and dry-run uses.
    WINDOWS_UNC is the production shape decided in ADR-020 — implemented but
    not yet validated against a real SMB share (see the connector runbook).
    """

    LOCAL_FAKE = "LOCAL_FAKE"
    WINDOWS_UNC = "WINDOWS_UNC"


class SourceHealth(str, enum.Enum):
    HEALTHY = "HEALTHY"
    UNREACHABLE = "UNREACHABLE"
    ACCESS_DENIED = "ACCESS_DENIED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class DiscoveryStatus(str, enum.Enum):
    """A file is only ever CONFIRMED_MISSING after a scan that actually
    covered its subtree succeeded (addendum §3.1) — never inferred from an
    unreachable source or a failed subtree.
    """

    PRESENT = "PRESENT"
    MISSING_CANDIDATE = "MISSING_CANDIDATE"
    CONFIRMED_MISSING = "CONFIRMED_MISSING"


class EntryAccessStatus(str, enum.Enum):
    """Network error, access denied, and not-found are distinct statuses per
    the requirements doc — never collapsed into one generic "failed"."""

    OK = "OK"
    ACCESS_DENIED = "ACCESS_DENIED"
    NETWORK_ERROR = "NETWORK_ERROR"
    NOT_FOUND = "NOT_FOUND"


class ScanRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class SourceRoot(Base):
    __tablename__ = "source_roots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="lan_source_type"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # For LOCAL_FAKE: a filesystem path. For WINDOWS_UNC: the UNC root
    # (\\host\share\subpath) — never a mapped drive letter (ADR-020).
    root_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Explicit subtree allowlist under root_path — NULL means the whole root
    # is in scope. A merged folder of shortcuts must register each real
    # target as its own SourceRoot rather than relying on this to expand
    # scope (addendum §3 — shortcuts are never auto-followed).
    allowed_subtrees: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # A reference into whatever secret store the deployment uses — never the
    # credential itself (spec-wide rule: no hardcoded/inline secrets).
    credential_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    health: Mapped[SourceHealth] = mapped_column(
        SAEnum(SourceHealth, name="lan_source_health"),
        nullable=False,
        default=SourceHealth.UNKNOWN,
    )
    health_checked_at: Mapped[datetime | None] = mapped_column(
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


class SourceEntry(Base):
    __tablename__ = "source_entries"
    __table_args__ = (
        UniqueConstraint("source_root_id", "normalized_path", name="uq_source_entry_root_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    source_root_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_roots.id"), nullable=False
    )
    # Normalized (case-folded per source semantics, separator-normalized)
    # path relative to source_root.root_path — the natural identity within
    # a root, since a plain filesystem exposes no other stable file ID.
    normalized_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_runs.id"), nullable=True
    )
    discovery_status: Mapped[DiscoveryStatus] = mapped_column(
        SAEnum(DiscoveryStatus, name="lan_discovery_status"),
        nullable=False,
        default=DiscoveryStatus.PRESENT,
    )
    access_status: Mapped[EntryAccessStatus] = mapped_column(
        SAEnum(EntryAccessStatus, name="lan_entry_access_status"),
        nullable=False,
        default=EntryAccessStatus.OK,
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


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    source_root_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_roots.id"), nullable=False
    )
    status: Mapped[ScanRunStatus] = mapped_column(
        SAEnum(ScanRunStatus, name="lan_scan_run_status"),
        nullable=False,
        default=ScanRunStatus.RUNNING,
    )
    # Resume checkpoint: {"subtree": ..., "page_cursor": ...} — opaque to
    # apps/api, owned and interpreted entirely by the worker's adapter.
    cursor: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    entries_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entries_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entries_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # List of {"subtree": ..., "error_type": ..., "message": ...} — a
    # populated list with status=PARTIAL is expected/safe, not a failure.
    error_summary: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
