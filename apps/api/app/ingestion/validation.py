import re
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

_PDF_MAGIC = b"%PDF-"
_DOCX_MAGIC = b"PK\x03\x04"

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadValidationError(ValueError):
    pass


def validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"Unsupported file type '{extension}'. Only PDF/DOCX allowed.")
    return extension


def validate_magic_bytes(extension: str, content: bytes) -> None:
    if extension == ".pdf" and not content.startswith(_PDF_MAGIC):
        raise UploadValidationError("File content does not match a valid PDF.")
    if extension == ".docx" and not content.startswith(_DOCX_MAGIC):
        raise UploadValidationError("File content does not match a valid DOCX.")


def validate_size(content: bytes, max_file_size_mb: int) -> None:
    max_bytes = max_file_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise UploadValidationError(f"File exceeds the maximum size of {max_file_size_mb}MB.")


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    sanitized = _SAFE_FILENAME_RE.sub("_", name)
    return sanitized or "file"


def mime_type_for_extension(extension: str) -> str:
    return _MIME_TYPES.get(extension, "application/octet-stream")
