"""Cross-process answer-cache invalidation (ADR-018).

apps/api/app/caching/answer_cache.py owns the AnswerCacheService, but this
worker is a separate Python process with its own venv and no import path to
apps/api's code (same constraint noted in ADR-017). Rather than standing up a
pub/sub channel and a background subscriber in apps/api, this mirrors
AnswerCacheService's own Redis key schema directly against the Redis instance
both processes already share: `answer_cache:{organization_id}:{chatbot_id}:
{query_digest}`. Deleting by the `answer_cache:{organization_id}:*` prefix is
exactly what `AnswerCacheService.invalidate_organization()` does — this is
the same operation, reimplemented here because it can't be imported.

If the key schema in answer_cache.py ever changes, this must change with it.
"""

import logging
import uuid

from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)

_ANSWER_CACHE_KEY_PREFIX = "answer_cache"


async def invalidate_answer_cache(organization_id: uuid.UUID) -> None:
    """Called whenever a document version reaches ACTIVE (fresh publish or
    M13 auto-supersede) — closes the gap ADR-017 accepted as TTL-only.
    Best-effort: a Redis hiccup here must not fail the indexing job that
    already committed the version's ACTIVE status; TTL remains the fallback
    bound on staleness if this fails.
    """
    pattern = f"{_ANSWER_CACHE_KEY_PREFIX}:{organization_id}:*"
    try:
        async for key in redis_client.scan_iter(match=pattern):
            await redis_client.delete(key)
    except Exception:
        logger.warning(
            "Answer-cache invalidation failed for organization %s; falling back to TTL expiry.",
            organization_id,
            exc_info=True,
        )
