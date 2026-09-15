"""Parent expansion (spec §23): "Neighbor expansion dilakukan jika relevan
... Jangan selalu mengambil previous dan next chunk tanpa reason." Only
parent expansion is implemented — a small fragment (e.g. a lone Ayat/Huruf
line) likely needs its parent's heading to stand alone as evidence. There is
no similarly clear, narrow trigger for previous/next sibling expansion, so
that is intentionally not implemented here.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.models import DocumentChunk
from app.retrieval.schemas import RetrievedChunk

# Not a spec-given number — a tunable module constant (like rrf.py's
# _DEFAULT_K), not a config knob.
_EXPANSION_TOKEN_THRESHOLD = 40


async def batch_expand_with_parents(
    db: AsyncSession, chunks: list[RetrievedChunk]
) -> dict[uuid.UUID, str]:
    """Maps each expansion-eligible chunk's own chunk_id to its parent's
    original_text, fetching every needed parent in a single query instead of
    one query per evidence item.
    """
    parent_ids_by_chunk_id = {
        chunk.chunk_id: chunk.parent_chunk_id
        for chunk in chunks
        if chunk.parent_chunk_id is not None and chunk.token_count < _EXPANSION_TOKEN_THRESHOLD
    }
    if not parent_ids_by_chunk_id:
        return {}

    distinct_parent_ids = set(parent_ids_by_chunk_id.values())
    rows = (
        await db.execute(
            select(DocumentChunk.id, DocumentChunk.original_text).where(
                DocumentChunk.id.in_(distinct_parent_ids)
            )
        )
    ).all()
    parent_text_by_parent_id = {row.id: row.original_text for row in rows}

    return {
        chunk_id: parent_text_by_parent_id[parent_id]
        for chunk_id, parent_id in parent_ids_by_chunk_id.items()
        if parent_id in parent_text_by_parent_id
    }
