"""Pure, DB-free tests for LAN-M2's staging helpers (promotion.py)."""

import pytest

from app.sources.local_fake_adapter import LocalFakeAdapter
from app.sources.promotion import (
    DiskWatermarkError,
    FileTooLargeError,
    FileUnstableError,
    check_disk_watermark,
    check_file_stable,
    extension_for_path,
    is_lock_or_temp_file,
    mime_type_for_extension,
    sanitize_filename,
    stage_to_temp_file,
)


def test_extension_and_mime_type():
    assert extension_for_path("sub/dir/a.PDF") == ".pdf"
    assert mime_type_for_extension(".pdf") == "application/pdf"
    assert mime_type_for_extension(".docx").startswith("application/vnd.openxml")
    assert mime_type_for_extension(".xyz") == "application/octet-stream"


def test_sanitize_filename_strips_unsafe_characters():
    assert sanitize_filename("sub/dir/Report (Final)!.pdf") == "Report__Final__.pdf"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("sub/~$report.docx", True),
        ("sub/report.docx.tmp", True),
        ("sub/report.docx", False),
        ("sub/report.pdf", False),
    ],
)
def test_is_lock_or_temp_file(path, expected):
    assert is_lock_or_temp_file(path) is expected


def test_check_disk_watermark_raises_when_below_threshold(tmp_path, monkeypatch):
    import shutil as shutil_module

    class _Usage:
        free = 100 * 1024 * 1024  # 100MB

    monkeypatch.setattr(shutil_module, "disk_usage", lambda _path: _Usage())

    with pytest.raises(DiskWatermarkError):
        check_disk_watermark(str(tmp_path), min_free_mb=2048)


def test_check_disk_watermark_passes_when_above_threshold(tmp_path):
    check_disk_watermark(str(tmp_path), min_free_mb=1)  # should not raise


def test_check_file_stable_returns_stat_when_unchanged(tmp_path):
    (tmp_path / "a.pdf").write_text("stable content")
    adapter = LocalFakeAdapter(str(tmp_path))

    result = check_file_stable(adapter, "a.pdf", window_seconds=0)

    assert result.exists is True
    assert result.size_bytes == len("stable content")


def test_check_file_stable_raises_when_size_changes_between_checks(tmp_path, monkeypatch):
    (tmp_path / "a.pdf").write_text("initial")
    adapter = LocalFakeAdapter(str(tmp_path))

    real_stat = adapter.stat
    call_count = {"n": 0}

    def flaky_stat(path):
        call_count["n"] += 1
        if call_count["n"] == 2:
            (tmp_path / "a.pdf").write_text("changed content, different size")
        return real_stat(path)

    monkeypatch.setattr(adapter, "stat", flaky_stat)

    with pytest.raises(FileUnstableError):
        check_file_stable(adapter, "a.pdf", window_seconds=0)


def test_check_file_stable_raises_when_file_disappears(tmp_path):
    adapter = LocalFakeAdapter(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        check_file_stable(adapter, "does-not-exist.pdf", window_seconds=0)


def test_stage_to_temp_file_computes_correct_hash_and_size(tmp_path):
    content = b"hello regulatory world" * 1000
    (tmp_path / "a.pdf").write_bytes(content)
    adapter = LocalFakeAdapter(str(tmp_path))
    staging_dir = str(tmp_path / "staging")

    import hashlib

    staged = stage_to_temp_file(adapter, "a.pdf", staging_dir, max_size_bytes=10 * 1024 * 1024)

    try:
        assert staged.size_bytes == len(content)
        assert staged.sha256_hex == hashlib.sha256(content).hexdigest()
        with open(staged.temp_path, "rb") as f:
            assert f.read() == content
    finally:
        import os

        if os.path.exists(staged.temp_path):
            os.remove(staged.temp_path)


def test_stage_to_temp_file_raises_and_cleans_up_when_too_large(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"x" * 5000)
    adapter = LocalFakeAdapter(str(tmp_path))
    staging_dir = str(tmp_path / "staging")

    with pytest.raises(FileTooLargeError):
        stage_to_temp_file(adapter, "a.pdf", staging_dir, max_size_bytes=100)

    import os

    assert os.listdir(staging_dir) == []
