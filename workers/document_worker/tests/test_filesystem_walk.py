"""Unit tests for the shared paginated filesystem walker (gap audit
2026-09-15) — a real UNC path can drop mid-enumeration on any per-child
call (`is_symlink`/`is_dir`/`stat`), not just the directory-listing call
already guarded before this pass.
"""

import os
from types import SimpleNamespace

from app.sources._filesystem_walk import paged_walk
from app.sources.adapter import EntryAccessStatus


class _FakeDirEntry:
    def __init__(
        self,
        name: str,
        *,
        is_dir: bool = False,
        is_symlink: bool = False,
        stat_error: Exception | None = None,
        size: int = 100,
        mtime: float = 0.0,
    ) -> None:
        self.name = name
        self._is_dir = is_dir
        self._is_symlink = is_symlink
        self._stat_error = stat_error
        self._size = size
        self._mtime = mtime

    def is_symlink(self) -> bool:
        return self._is_symlink

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        return self._is_dir

    def stat(self, *, follow_symlinks: bool = True) -> SimpleNamespace:
        if self._stat_error is not None:
            raise self._stat_error
        return SimpleNamespace(st_size=self._size, st_mtime=self._mtime)


class _FakeScandirContext:
    def __init__(self, entries: list[_FakeDirEntry]) -> None:
        self._entries = entries

    def __enter__(self):
        return iter(self._entries)

    def __exit__(self, *args: object) -> bool:
        return False


def test_a_childs_stat_raising_os_error_is_skipped_not_fatal(monkeypatch) -> None:
    entries = [
        _FakeDirEntry("good.pdf", size=10, mtime=1.0),
        _FakeDirEntry("bad.pdf", stat_error=OSError("simulated network drop")),
        _FakeDirEntry("good2.pdf", size=20, mtime=2.0),
    ]
    monkeypatch.setattr(os, "scandir", lambda path: _FakeScandirContext(entries))

    page = paged_walk("/fake/root", "", None, page_size=10)

    assert [e.normalized_path for e in page.entries] == ["good.pdf", "good2.pdf"]
    assert len(page.errors) == 1
    assert page.errors[0].subtree == "bad.pdf"
    assert page.errors[0].error_type == EntryAccessStatus.NETWORK_ERROR
    assert page.next_cursor is None


def test_a_childs_is_dir_raising_os_error_is_also_skipped_not_fatal(monkeypatch) -> None:
    # is_symlink()/is_dir() are checked before stat() per-child — a network
    # drop can surface on any of the three, not just the last one.
    class _RaisingIsDirEntry(_FakeDirEntry):
        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            raise OSError("simulated network drop")

    entries = [_FakeDirEntry("good.pdf", size=10), _RaisingIsDirEntry("bad-dir")]
    monkeypatch.setattr(os, "scandir", lambda path: _FakeScandirContext(entries))

    page = paged_walk("/fake/root", "", None, page_size=10)

    assert [e.normalized_path for e in page.entries] == ["good.pdf"]
    assert len(page.errors) == 1
    assert page.errors[0].subtree == "bad-dir"
