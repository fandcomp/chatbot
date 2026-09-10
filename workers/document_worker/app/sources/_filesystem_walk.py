"""Shared directory-at-a-time paginated walk used by both
`local_fake_adapter.py` and `windows_unc_adapter.py` — a UNC path is just a
string path to Python's `os` module on Windows, so the walk logic is
identical; only host/share allowlisting and path normalization differ
between the two adapters (see their own modules).

Bounded-memory strategy (addendum §3.1's "streaming/paged enumeration,
never load the whole file list into RAM"): at most one directory's direct
children plus the stack of not-yet-visited directory paths are held in
memory at a time — never the whole subtree's file list. A single very
large directory's children are still listed in one OS call (Python's
`os.scandir` offers no mid-directory continuation token), which is an
inherent OS-API limitation, not a gap in this walker; it is still far
below "load 4TB of file metadata at once."

Symlinks and reparse points are never traversed (loop/traversal
protection) — see `docs/operations/LAN_CONNECTOR_RUNBOOK.md` for why this
is a documented limitation, not silent mishandling.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from app.sources.adapter import DiscoveredEntry, EntryAccessStatus, ScanPage, SubtreeError


def _normalize_rel_path(path: str) -> str:
    # Forward slashes regardless of OS, case preserved (case-INsensitivity
    # is handled by callers that need it — Postgres uniqueness here is on
    # the literal normalized string, so a caller doing case-insensitive
    # matching must lower() before comparing, not this function).
    return path.replace(os.sep, "/").strip("/")


def paged_walk(root_path: str, subtree: str, cursor: dict | None, page_size: int) -> ScanPage:
    if cursor is None:
        pending_dirs: list[str] = [subtree]
        current_dir: str | None = None
        current_dir_offset = 0
    else:
        pending_dirs = list(cursor["pending_dirs"])
        current_dir = cursor["current_dir"]
        current_dir_offset = cursor["current_dir_offset"]

    entries: list[DiscoveredEntry] = []
    errors: list[SubtreeError] = []

    while len(entries) < page_size:
        if current_dir is None:
            if not pending_dirs:
                break
            current_dir = pending_dirs.pop()
            current_dir_offset = 0

        abs_dir = os.path.join(root_path, current_dir) if current_dir else root_path
        try:
            with os.scandir(abs_dir) as it:
                children = sorted(it, key=lambda entry: entry.name)
        except PermissionError as exc:
            errors.append(
                SubtreeError(current_dir, EntryAccessStatus.ACCESS_DENIED, str(exc))
            )
            current_dir = None
            continue
        except FileNotFoundError as exc:
            errors.append(SubtreeError(current_dir, EntryAccessStatus.NOT_FOUND, str(exc)))
            current_dir = None
            continue
        except OSError as exc:
            # Covers transient network errors reading a real UNC path
            # (unreachable host, dropped connection) — distinct from the
            # two cases above per the requirements doc's three-way split.
            errors.append(
                SubtreeError(current_dir, EntryAccessStatus.NETWORK_ERROR, str(exc))
            )
            current_dir = None
            continue

        while current_dir_offset < len(children) and len(entries) < page_size:
            child = children[current_dir_offset]
            current_dir_offset += 1
            rel_path = _normalize_rel_path(
                f"{current_dir}/{child.name}" if current_dir else child.name
            )
            if child.is_symlink():
                # Reparse points/symlinks are never traversed — see module
                # docstring. Not reported as an entry or an error: it's a
                # deliberate skip, not a failure.
                continue
            if child.is_dir(follow_symlinks=False):
                pending_dirs.append(rel_path)
                continue
            stat_result = child.stat(follow_symlinks=False)
            entries.append(
                DiscoveredEntry(
                    normalized_path=rel_path,
                    size_bytes=stat_result.st_size,
                    mtime=datetime.fromtimestamp(stat_result.st_mtime, tz=UTC),
                )
            )

        if current_dir_offset >= len(children):
            current_dir = None

    is_done = current_dir is None and not pending_dirs
    next_cursor = (
        None
        if is_done
        else {
            "pending_dirs": pending_dirs,
            "current_dir": current_dir,
            "current_dir_offset": current_dir_offset,
        }
    )
    return ScanPage(entries=entries, next_cursor=next_cursor, errors=errors)
