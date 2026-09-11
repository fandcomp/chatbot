"""LAN-M2 (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md §6) — pure staging
helpers used by `sources_tasks.py::promote_source_entry`. Deliberately
DB-free and adapter-only, same split as LAN-M1's discovery.py/
sources_tasks.py.

Extension/mime-type list mirrors apps/api/app/ingestion/validation.py's
ALLOWED_EXTENSIONS/_MIME_TYPES exactly (small, intentional duplication —
same cross-process pattern ADR-016 already accepts) — DOC is not yet
allowed because Docling has no DOC/DOCX-legacy support until LAN-M3.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass

from app.sources.adapter import SourceAdapter, StatResult

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")
_LOCK_OR_TEMP_RE = re.compile(r"(^|/)~\$|\.tmp$", re.IGNORECASE)

_CHUNK_SIZE = 1024 * 1024


class UnsupportedFileTypeError(Exception):
    pass


class FileUnstableError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class DiskWatermarkError(Exception):
    pass


def extension_for_path(normalized_path: str) -> str:
    return os.path.splitext(normalized_path)[1].lower()


def mime_type_for_extension(extension: str) -> str:
    return _MIME_TYPES.get(extension, "application/octet-stream")


def sanitize_filename(normalized_path: str) -> str:
    base = os.path.basename(normalized_path)
    sanitized = _SAFE_FILENAME_RE.sub("_", base)
    return sanitized or "file"


def is_lock_or_temp_file(normalized_path: str) -> bool:
    return bool(_LOCK_OR_TEMP_RE.search(normalized_path))


def check_disk_watermark(staging_dir: str, min_free_mb: int) -> None:
    os.makedirs(staging_dir, exist_ok=True)
    free_bytes = shutil.disk_usage(staging_dir).free
    if free_bytes < min_free_mb * 1024 * 1024:
        raise DiskWatermarkError(
            f"free disk {free_bytes} bytes is below the {min_free_mb}MB watermark"
        )


def check_file_stable(
    adapter: SourceAdapter, normalized_path: str, window_seconds: int
) -> StatResult:
    """Two independent stats, `window_seconds` apart — a real sleep, not a
    scheduled follow-up task, per this milestone's documented scalability
    trade-off (see docs/LAN_ARCHIVE_PROGRESS.md): simple and correct for
    pilot-scale promotion volume, revisit if throughput ever demands a
    non-blocking two-phase check.
    """
    first = adapter.stat(normalized_path)
    if not first.exists:
        raise FileNotFoundError(normalized_path)
    time.sleep(window_seconds)
    second = adapter.stat(normalized_path)
    if not second.exists or second.size_bytes != first.size_bytes or second.mtime != first.mtime:
        raise FileUnstableError(normalized_path)
    return second


@dataclass(frozen=True)
class StagedFile:
    temp_path: str
    sha256_hex: str
    size_bytes: int


def stage_to_temp_file(
    adapter: SourceAdapter, normalized_path: str, staging_dir: str, max_size_bytes: int
) -> StagedFile:
    """Streams the adapter's bytes into a local temp file in bounded
    chunks, computing SHA-256 incrementally — never materializes the whole
    file in memory. Caller is responsible for deleting `temp_path` once
    done with it (success or failure of a later step)."""
    os.makedirs(staging_dir, exist_ok=True)
    temp_path = os.path.join(staging_dir, f"{uuid.uuid4().hex}.tmp")
    hasher = hashlib.sha256()
    size = 0
    try:
        with adapter.open_stream(normalized_path) as source, open(temp_path, "wb") as dest:
            while True:
                chunk = source.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size_bytes:
                    raise FileTooLargeError(
                        f"{normalized_path} exceeds max size of {max_size_bytes} bytes"
                    )
                hasher.update(chunk)
                dest.write(chunk)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return StagedFile(temp_path=temp_path, sha256_hex=hasher.hexdigest(), size_bytes=size)
