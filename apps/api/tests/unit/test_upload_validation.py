import pytest

from app.ingestion.validation import (
    UploadValidationError,
    mime_type_for_extension,
    read_within_limit,
    sanitize_filename,
    validate_extension,
    validate_magic_bytes,
    validate_size,
)

_PDF_BYTES = b"%PDF-1.4\n%test\n%%EOF"
_DOCX_BYTES = b"PK\x03\x04rest-of-a-zip-file"


class _FakeUpload:
    """Minimal ChunkedReadable stand-in — hands out up to `chunk_size` bytes
    per `.read()` call and counts how many calls were made, so a test can
    prove read_within_limit stopped pulling from the stream early rather
    than draining it fully before rejecting an oversized upload.
    """

    def __init__(self, total_size: int, chunk_size: int) -> None:
        self._remaining = total_size
        self._chunk_size = chunk_size
        self.read_calls = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self._remaining <= 0:
            return b""
        take = min(self._remaining, self._chunk_size, size if size > 0 else self._chunk_size)
        self._remaining -= take
        return b"x" * take


def test_validate_extension_accepts_pdf_and_docx() -> None:
    assert validate_extension("report.PDF") == ".pdf"
    assert validate_extension("report.docx") == ".docx"


def test_validate_extension_rejects_other_types() -> None:
    with pytest.raises(UploadValidationError):
        validate_extension("report.txt")


def test_validate_magic_bytes_accepts_matching_content() -> None:
    validate_magic_bytes(".pdf", _PDF_BYTES)
    validate_magic_bytes(".docx", _DOCX_BYTES)


def test_validate_magic_bytes_rejects_extension_content_mismatch() -> None:
    with pytest.raises(UploadValidationError):
        validate_magic_bytes(".pdf", _DOCX_BYTES)
    with pytest.raises(UploadValidationError):
        validate_magic_bytes(".docx", _PDF_BYTES)


def test_validate_size_rejects_oversized_content() -> None:
    with pytest.raises(UploadValidationError):
        validate_size(b"x" * 10, max_file_size_mb=0)


def test_validate_size_accepts_content_within_limit() -> None:
    validate_size(b"x" * 10, max_file_size_mb=1)


def test_sanitize_filename_strips_path_and_unsafe_characters() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("my report (final)!.pdf") == "my_report__final__.pdf"


def test_mime_type_for_extension_known_and_unknown() -> None:
    assert mime_type_for_extension(".pdf") == "application/pdf"
    assert mime_type_for_extension(".unknown") == "application/octet-stream"


async def test_read_within_limit_returns_the_full_content_when_within_limit() -> None:
    fake = _FakeUpload(total_size=10, chunk_size=1024 * 1024)
    result = await read_within_limit(fake, max_file_size_mb=1)
    assert result == b"x" * 10


async def test_read_within_limit_rejects_content_over_the_limit() -> None:
    fake = _FakeUpload(total_size=2 * 1024 * 1024, chunk_size=1024 * 1024)
    with pytest.raises(UploadValidationError):
        await read_within_limit(fake, max_file_size_mb=1)


async def test_read_within_limit_stops_reading_once_the_cap_is_exceeded() -> None:
    # Regression test for a real memory-exhaustion DoS gap: the previous
    # `await file.read()` (no size argument) fully buffered an upload into
    # memory before ever checking its size. A 500MB stream against a 1MB
    # cap must abort after only a couple of chunks, never pulling anywhere
    # close to the full stream.
    huge_total = 500 * 1024 * 1024
    fake = _FakeUpload(total_size=huge_total, chunk_size=1024 * 1024)

    with pytest.raises(UploadValidationError):
        await read_within_limit(fake, max_file_size_mb=1)

    assert fake.read_calls <= 5
