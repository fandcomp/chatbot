"""ADR-008's EmbeddingGateway — the worker's only Voyage touchpoint.

Embeds `contextual_text` (not `original_text` — addendum §24.2, ADR-008)
using Voyage's contextualized_embed, which takes one inner list per
*document* (all its chunks together, in order) and returns embeddings
aligned to that same order. `embed_query` (query-time embedding) is a
different process's concern (apps/api, M7) and does not belong here.
"""

import asyncio

import voyageai
from voyageai.error import RateLimitError

from app.core.config import settings

# A single contextualized_embed call sends every chunk in one request; an
# unbatched large document (300+ chunks) reliably exceeds Voyage's per-minute
# token cap in one shot, so no retry/backoff at the caller can ever succeed
# without splitting the request itself. Batching trades this off against
# losing cross-batch context (chunks in a later batch no longer see earlier
# batches' chunks as context) — an accepted, documented tradeoff rather than
# an unbounded single request.
_MAX_CHUNKS_PER_BATCH = 50

# A multi-batch document on Voyage's pre-payment-method tier (3 requests per
# minute) will routinely 429 on batch 2+ even right after a successful batch
# 1. Celery's task-level autoretry_for is the wrong tool for this specific
# case: its default retry_backoff applies jitter (randomized short delays),
# which can exhaust max_retries in seconds without ever waiting out a
# per-minute window — and a task-level retry re-embeds every batch from
# scratch, wasting the ones that already succeeded. Retrying the single
# failed batch here, with a fixed wait comfortably over the 60s/3 window,
# is what actually clears the limit; Celery's autoretry_for stays as a
# backstop for outages longer than this budget.
_RATE_LIMIT_MAX_ATTEMPTS = 4
_RATE_LIMIT_RETRY_WAIT_SECONDS = 22


class EmbeddingGateway:
    def __init__(self) -> None:
        self._client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        for attempt in range(1, _RATE_LIMIT_MAX_ATTEMPTS + 1):
            try:
                result = await self._client.contextualized_embed(
                    inputs=[batch],
                    model=settings.EMBEDDING_MODEL,
                    input_type="document",
                    output_dimension=settings.VOYAGE_EMBEDDING_DIMENSION,
                )
                return list(result.results[0].embeddings)
            except RateLimitError:
                if attempt == _RATE_LIMIT_MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(_RATE_LIMIT_RETRY_WAIT_SECONDS)
        raise AssertionError("unreachable")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), _MAX_CHUNKS_PER_BATCH):
            batch = texts[start : start + _MAX_CHUNKS_PER_BATCH]
            embeddings.extend(await self._embed_batch(batch))
        return embeddings
