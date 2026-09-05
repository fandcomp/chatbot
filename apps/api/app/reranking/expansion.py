"""Parent expansion (spec §23): "Neighbor expansion dilakukan jika relevan
... Jangan selalu mengambil previous dan next chunk tanpa reason." Only
parent expansion is implemented — a small fragment (e.g. a lone Ayat/Huruf
line) likely needs its parent's heading to stand alone as evidence. There is
no similarly clear, narrow trigger for previous/next sibling expansion, so
that is intentionally not implemented here.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.models import DocumentChunk
from app.retrieval.schemas import RetrievedChunk

# Not a spec-given number — a tunable module constant (like rrf.py's
# _DEFAULT_K), not a config knob.
_EXPANSION_TOKEN_THRESHOLD = 40


async def maybe_expand_with_parent(db: AsyncSession, chunk: RetrievedChunk) -> str | None:
    if chunk.parent_chunk_id is None or chunk.token_count >= _EXPANSION_TOKEN_THRESHOLD:
        return None

    parent = (
        await db.execute(select(DocumentChunk).where(DocumentChunk.id == chunk.parent_chunk_id))
    ).scalar_one_or_none()
    return parent.original_text if parent is not None else None
