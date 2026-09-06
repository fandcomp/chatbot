"""Shared async Redis client (app/api/health.py's own ad-hoc `redis.from_url`
call is fine for a one-shot health ping, but app code that hits Redis on
every request — the answer cache — should reuse one pooled client rather
than opening a new connection per call).
"""

import redis.asyncio as redis

from app.core.config import settings

redis_client: redis.Redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
