import uuid
from typing import Literal

from pydantic import BaseModel

RetrievalMode = Literal["EXACT_STRUCTURAL", "HYBRID"]


class RetrievalRequest(BaseModel):
    query: str
    knowledge_space_id: uuid.UUID | None = None


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    structural_path_text: str | None
    # Evidence/citation source (addendum §24.1) — never contextual_text,
    # which carries embedding-only "Dokumen:/BAB:/Isi:" boilerplate.
    original_text: str
    page_start: int
    page_end: int
    sequence_number: int
    score: float | None
    # M8's parent expansion (spec §23) needs these to decide whether a chunk
    # is a small enough fragment to warrant pulling in its parent's text.
    parent_chunk_id: uuid.UUID | None
    token_count: int


class RetrievalResponse(BaseModel):
    query: str
    mode: RetrievalMode
    chunks: list[RetrievedChunk]
