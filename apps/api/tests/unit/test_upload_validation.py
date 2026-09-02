import pytest

from app.ingestion.validation import (
    UploadValidationError,
    mime_type_for_extension,
    sanitize_filename,
    validate_extension,
    validate_magic_bytes,
    validate_size,
)

_PDF_BYTES = b"%PDF-1.4\n%test\n%%EOF"
_DOCX_BYTES = b"PK\x03\x04rest-of-a-zip-file"


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
