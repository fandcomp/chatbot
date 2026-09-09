"""Shared async Redis client, mirroring apps/api/app/core/redis_client.py's
own pooled-client rationale — used here only for cross-process answer-cache
invalidation (ADR-018), not as the Celery broker (celery_app.py opens its own
connection for that)."""

import redis.asyncio as redis

from app.core.config import settings

redis_client: redis.Redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
