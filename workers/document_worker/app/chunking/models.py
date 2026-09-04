"""In-memory representation of a chunk being built, before persistence.
Mirrors the columns `document_chunks` will store.
"""

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class ChunkSpec:
    id: uuid.UUID
    source_node_id: uuid.UUID
    parent_chunk_id: uuid.UUID | None
    depth: int
    sequence_number: int
    page_start: int
    page_end: int
    original_text: str
    structural_path_json: list[dict[str, Any]]
    structural_path_text: str | None
    token_count: int
    contextual_text: str = ""
    previous_chunk_id: uuid.UUID | None = None
    next_chunk_id: uuid.UUID | None = None
