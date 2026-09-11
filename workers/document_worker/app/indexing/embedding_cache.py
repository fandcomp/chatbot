"""LAN-M3 (addendum §5) — embedding cache. Keyed on `contextual_text` (which
already carries the structural Document/BAB/Pasal prefix baked in, per
`chunking/contextual_text.py`) plus the embedding config that produced it, so
an unchanged chunk never gets re-embedded across document versions or
duplicate-content promotions. Global, not tenant-scoped — content-addressable
by design, mirroring LAN-M2's content-hash storage dedup.

Cache writes use their own short session, independent of the caller's
job-processing transaction: a successfully computed embedding is worth
keeping even if the indexing job later fails at the Qdrant-upsert step.
"""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import embedding_cache_entries


def cache_key_for(contextual_text: str) -> str:
    payload = "|".join(
        [
            contextual_text,
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_MODEL_REVISION,
            str(settings.VOYAGE_EMBEDDING_DIMENSION),
            str(settings.EMBEDDING_NORMALIZED),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_cached_embeddings(
    session: AsyncSession, cache_keys: list[str]
) -> dict[str, list[float]]:
    if not cache_keys:
        return {}
    rows = (
        await session.execute(
            select(
                embedding_cache_entries.c.cache_key, embedding_cache_entries.c.embedding
            ).where(embedding_cache_entries.c.cache_key.in_(cache_keys))
        )
    ).all()
    return {row.cache_key: list(row.embedding) for row in rows}


async def store_embeddings(
    session: AsyncSession, entries: list[tuple[str, list[float]]]
) -> None:
    if not entries:
        return
    now = datetime.now(UTC)
    stmt = (
        pg_insert(embedding_cache_entries)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "cache_key": cache_key,
                    "model": settings.EMBEDDING_MODEL,
                    "revision": settings.EMBEDDING_MODEL_REVISION,
                    "dimension": settings.VOYAGE_EMBEDDING_DIMENSION,
                    "normalized": settings.EMBEDDING_NORMALIZED,
                    "embedding": embedding,
                    "created_at": now,
                }
                for cache_key, embedding in entries
            ]
        )
        # Two workers racing to cache the same text/config: the loser no-ops
        # rather than erroring on the unique cache_key constraint.
        .on_conflict_do_nothing(index_elements=["cache_key"])
    )
    await session.execute(stmt)
    await session.commit()
