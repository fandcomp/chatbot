"""Pure, DB-free tests for the filesystem walk and discovery-page driver
(LAN-M1). Uses a real temp directory — no client data, no network.
"""

import os

from app.sources._filesystem_walk import paged_walk
from app.sources.discovery import run_one_page
from app.sources.local_fake_adapter import LocalFakeAdapter


def _make_tree(root, layout: dict) -> None:
    """layout: {"a.txt": "content", "sub/b.txt": "content", ...}"""
    for rel_path, content in layout.items():
        full_path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)


def test_paged_walk_finds_all_files_across_nested_directories(tmp_path):
    _make_tree(
        str(tmp_path),
        {"a.txt": "1", "sub/b.txt": "22", "sub/nested/c.txt": "333"},
    )

    page = paged_walk(str(tmp_path), "", None, page_size=100)

    assert page.next_cursor is None
    assert {e.normalized_path for e in page.entries} == {"a.txt", "sub/b.txt", "sub/nested/c.txt"}
    sizes = {e.normalized_path: e.size_bytes for e in page.entries}
    assert sizes["a.txt"] == 1
    assert sizes["sub/nested/c.txt"] == 3


def test_paged_walk_stays_within_page_size_and_resumes_via_cursor(tmp_path):
    _make_tree(str(tmp_path), {f"file{i}.txt": "x" for i in range(10)})

    seen = []
    cursor = None
    for _ in range(20):
        page = paged_walk(str(tmp_path), "", cursor, page_size=3)
        assert len(page.entries) <= 3
        seen.extend(e.normalized_path for e in page.entries)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None
    assert sorted(seen) == sorted(f"file{i}.txt" for i in range(10))
    assert len(seen) == len(set(seen))  # no duplicates across pages


def test_paged_walk_records_access_denied_without_crashing(tmp_path, monkeypatch):
    _make_tree(str(tmp_path), {"ok/a.txt": "1"})
    restricted_dir = tmp_path / "restricted"
    restricted_dir.mkdir()

    real_scandir = os.scandir

    def fake_scandir(path):
        if "restricted" in str(path):
            raise PermissionError("access denied (simulated)")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    page = paged_walk(str(tmp_path), "", None, page_size=100)

    assert any(e.subtree == "restricted" for e in page.errors)
    # The accessible sibling directory must still be scanned — one bad
    # subtree does not poison the rest.
    assert "ok/a.txt" in {e.normalized_path for e in page.entries}


def test_paged_walk_does_not_follow_symlinks(tmp_path):
    target = tmp_path / "real_target"
    target.mkdir()
    (target / "inside.txt").write_text("x")
    link = tmp_path / "link_to_target"
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        import pytest

        pytest.skip("symlink creation not permitted in this environment")

    page = paged_walk(str(tmp_path), "", None, page_size=100)

    normalized = {e.normalized_path for e in page.entries}
    assert "real_target/inside.txt" in normalized
    assert "link_to_target/inside.txt" not in normalized


def test_run_one_page_advances_through_multiple_subtrees(tmp_path):
    _make_tree(str(tmp_path), {"root_a/x.txt": "1", "root_b/y.txt": "22"})
    adapter = LocalFakeAdapter(str(tmp_path))
    subtrees = ["root_a", "root_b"]

    seen = []
    cursor = None
    for _ in range(10):
        result = run_one_page(adapter, subtrees, cursor, page_size=1)
        seen.extend(e.normalized_path for e in result.entries)
        cursor = result.next_cursor
        if result.done:
            break

    assert sorted(seen) == ["root_a/x.txt", "root_b/y.txt"]


def test_run_one_page_with_empty_subtree_list_is_immediately_done():
    adapter = LocalFakeAdapter("/does/not/matter")
    result = run_one_page(adapter, [], None, page_size=10)
    assert result.done is True
    assert result.entries == []
