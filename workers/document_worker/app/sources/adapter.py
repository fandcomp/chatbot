"""LAN-M1 source adapter contract (ADR-020, docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md
§3). Deliberately a small `Protocol`, not a heavy ABC hierarchy — the LAN
requirements doc explicitly asks to avoid over-abstraction. Any adapter
(local, Windows UNC, or a future Windows-Service-backed remote adapter per
ADR-020's "Consequences") implements this same shape.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class EntryAccessStatus(str, enum.Enum):
    """Mirrors apps/api/app/sources/models.py's EntryAccessStatus — kept as
    a plain string enum here (not imported) since this worker has no import
    path to apps/api, matching the cross-process pattern already accepted
    for other tables (ADR-016)."""

    OK = "OK"
    ACCESS_DENIED = "ACCESS_DENIED"
    NETWORK_ERROR = "NETWORK_ERROR"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class DiscoveredEntry:
    normalized_path: str
    size_bytes: int
    mtime: datetime | None
    access_status: EntryAccessStatus = EntryAccessStatus.OK


@dataclass(frozen=True)
class SubtreeError:
    subtree: str
    error_type: EntryAccessStatus
    message: str


@dataclass(frozen=True)
class ScanPage:
    entries: list[DiscoveredEntry]
    # Opaque to callers other than the adapter that produced it. None means
    # this subtree's walk is complete (not that the whole scan is done —
    # discovery.py drives the outer loop across configured subtrees).
    next_cursor: dict | None
    errors: list[SubtreeError] = field(default_factory=list)


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str


class SourceAdapter(Protocol):
    def check_health(self) -> HealthStatus: ...

    def paged_scan(self, subtree: str, cursor: dict | None, page_size: int) -> ScanPage:
        """Returns up to `page_size` entries starting from `cursor` (None to
        start a subtree from the beginning). Must never load an entire
        subtree's file list into memory — see `_filesystem_walk.py` for the
        directory-at-a-time strategy both filesystem-backed adapters share.
        """
        ...

    def open_stream(self, normalized_path: str):
        """Unused until LAN-M2 (snapshot/transfer) — defined now so the
        contract is stable when that milestone lands."""
        ...
