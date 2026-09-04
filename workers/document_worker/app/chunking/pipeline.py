"""Orchestrates M5: load a document version's nodes, build the chunk tree,
render contextual text for every chunk. Consumes M4's persisted rows (read
back from Postgres by the caller — see tasks.py's `_chunk_document_async`),
same reasoning as M4's `interpret_structure` pipeline: independent
invokability/testability at the cost of one extra DB round-trip.
"""

from dataclasses import dataclass
from typing import Any

from app.chunking.chunk_builder import ChunkableNode, build_chunks
from app.chunking.contextual_text import render_contextual_text
from app.chunking.models import ChunkSpec


@dataclass
class ChunkingResult:
    chunks: list[ChunkSpec]


def build_document_chunks(
    node_rows: list[dict[str, Any]], document_title: str
) -> ChunkingResult:
    nodes = [ChunkableNode.from_row(row) for row in node_rows]
    chunks = build_chunks(nodes)
    for chunk in chunks:
        chunk.contextual_text = render_contextual_text(
            document_title, chunk.structural_path_json, chunk.original_text
        )
    return ChunkingResult(chunks=chunks)
