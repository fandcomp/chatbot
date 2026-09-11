"""The adapter every automated test and local dry-run uses (LAN-M1).
Reads a real local directory tree — no network, no allowlist, no UNC
semantics. Registered as `SourceType.LOCAL_FAKE` in apps/api.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import BinaryIO

from app.sources._filesystem_walk import paged_walk
from app.sources.adapter import HealthStatus, ScanPage, StatResult


class LocalFakeAdapter:
    def __init__(self, root_path: str) -> None:
        self._root_path = root_path

    def check_health(self) -> HealthStatus:
        if not os.path.isdir(self._root_path):
            return HealthStatus(healthy=False, detail=f"root not found: {self._root_path}")
        return HealthStatus(healthy=True, detail="ok")

    def paged_scan(self, subtree: str, cursor: dict | None, page_size: int) -> ScanPage:
        return paged_walk(self._root_path, subtree, cursor, page_size)

    def stat(self, normalized_path: str) -> StatResult:
        full_path = os.path.join(self._root_path, normalized_path)
        try:
            result = os.stat(full_path, follow_symlinks=False)
        except OSError:
            return StatResult(exists=False, size_bytes=None, mtime=None)
        return StatResult(
            exists=True,
            size_bytes=result.st_size,
            mtime=datetime.fromtimestamp(result.st_mtime, tz=UTC),
        )

    def open_stream(self, normalized_path: str) -> BinaryIO:
        full_path = os.path.join(self._root_path, normalized_path)
        return open(full_path, "rb")
