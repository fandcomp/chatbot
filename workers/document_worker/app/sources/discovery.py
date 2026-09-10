"""Drives a discovery scan across a `SourceRoot`'s configured subtrees, one
page at a time. Deliberately DB-free and adapter-agnostic (pure function,
easy to unit test) — `sources_tasks.py` is the thin layer that persists each
page's results and checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.sources.adapter import DiscoveredEntry, ScanPage, SourceAdapter, SubtreeError


@dataclass(frozen=True)
class DiscoveryPageResult:
    entries: list[DiscoveredEntry]
    errors: list[SubtreeError]
    next_cursor: dict | None
    done: bool


def run_one_page(
    adapter: SourceAdapter,
    subtrees: list[str],
    outer_cursor: dict | None,
    page_size: int,
) -> DiscoveryPageResult:
    """`subtrees` is `SourceRoot.allowed_subtrees` or `[""]` for the whole
    root. `outer_cursor` is `{"subtree_index": int, "walk_cursor": dict |
    None}` — opaque to callers, persisted verbatim in `ScanRun.cursor`.
    """
    if not subtrees:
        return DiscoveryPageResult(entries=[], errors=[], next_cursor=None, done=True)

    if outer_cursor is None:
        subtree_index = 0
        walk_cursor: dict | None = None
    else:
        subtree_index = outer_cursor["subtree_index"]
        walk_cursor = outer_cursor["walk_cursor"]

    if subtree_index >= len(subtrees):
        return DiscoveryPageResult(entries=[], errors=[], next_cursor=None, done=True)

    page: ScanPage = adapter.paged_scan(subtrees[subtree_index], walk_cursor, page_size)

    if page.next_cursor is not None:
        # Current subtree isn't finished — stay on it.
        next_outer_cursor: dict | None = {
            "subtree_index": subtree_index,
            "walk_cursor": page.next_cursor,
        }
        return DiscoveryPageResult(
            entries=page.entries, errors=page.errors, next_cursor=next_outer_cursor, done=False
        )

    # This subtree finished (successfully or via a recorded error) — advance.
    next_subtree_index = subtree_index + 1
    if next_subtree_index >= len(subtrees):
        return DiscoveryPageResult(
            entries=page.entries, errors=page.errors, next_cursor=None, done=True
        )
    return DiscoveryPageResult(
        entries=page.entries,
        errors=page.errors,
        next_cursor={"subtree_index": next_subtree_index, "walk_cursor": None},
        done=False,
    )
