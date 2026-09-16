import re
from pathlib import Path
from typing import Protocol

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

_PDF_MAGIC = b"%PDF-"
_DOCX_MAGIC = b"PK\x03\x04"

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Not a spec-given number — a tunable module constant, like other cascade/
# threshold constants across this codebase.
_READ_CHUNK_BYTES = 1024 * 1024


class UploadValidationError(ValueError):
    pass


class ChunkedReadable(Protocol):
    """Structural type for anything read_within_limit can stream from —
    matches FastAPI/Starlette's UploadFile.read(size) without this
    framework-agnostic validation module importing FastAPI directly.
    """

    async def read(self, size: int = -1) -> bytes: ...


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


async def read_within_limit(file: ChunkedReadable, max_file_size_mb: int) -> bytes:
    """Reads `file` in bounded chunks, rejecting it as soon as the size cap
    is exceeded — never buffers an oversized upload fully into memory first
    and checks after (unlike calling `.read()` with no size argument, then
    `validate_size()` on the result). Any authenticated org member can
    upload, so an unbounded `await file.read()` was a real memory-exhaustion
    DoS vector: nothing rejected an oversized request until the entire body
    was already sitting in a single `bytes` object.
    """
    max_bytes = max_file_size_mb * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(f"File exceeds the maximum size of {max_file_size_mb}MB.")
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    sanitized = _SAFE_FILENAME_RE.sub("_", name)
    return sanitized or "file"


def mime_type_for_extension(extension: str) -> str:
    return _MIME_TYPES.get(extension, "application/octet-stream")
