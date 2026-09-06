"""AnswerCacheService (spec §45 Semantic Answer Cache, §47 rule 9) — caches a
validated chat answer so an identical repeated question skips retrieval,
reranking, and the LLM call entirely.

Scope decisions, recorded in ADR-017:

- Exact-normalized-query matching only, not true embedding-similarity
  semantic matching — "advanced caching" is explicitly post-MVP (spec
  §104). "Semantic" in the spec's section title refers to the answer being
  keyed by query meaning rather than raw conversation turn count, which an
  exact-normalized-text key already achieves for the common repeated-FAQ
  case this cache targets.
- Only used for a conversation's first turn (ChatService checks
  `conversation_context is None` before calling `get`/`set`) — a cache key
  built from `query_text` alone has no way to represent prior conversation
  context, so serving a cache hit to a follow-up question risks returning a
  contextually wrong answer.
- §45's cache key also lists `knowledge_base_version` and `access_scope`.
  Neither exists in this codebase yet: KnowledgeBaseVersion is deferred
  (M13), and there is no per-user knowledge-space ACL narrower than
  `organization_id` (every org member can query every knowledge space they
  belong to). The key below omits both accordingly.
- Invalidation only covers the two document-lifecycle events apps/api can
  reach synchronously in-process: archive (`documents/router.py`) and
  permanent delete. A new document version reaching ACTIVE (including
  auto-supersede) happens in workers/document_worker, a separate process
  with no connection to this cache — those transitions rely on
  `ANSWER_CACHE_TTL_SECONDS` alone to bound staleness. This is an accepted
  v1 gap, not a hidden one — see ADR-017 for what a cross-process
  invalidation channel (e.g. Redis pub/sub) would need to look like.
"""

import hashlib
import json
import uuid

import redis.asyncio as redis

from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.text import normalize_query_text
from app.verification.schemas import AnswerResponse

_KEY_PREFIX = "answer_cache"


class AnswerCacheService:
    def __init__(self, client: redis.Redis | None = None) -> None:
        self._redis = client or redis_client

    def _key(self, organization_id: uuid.UUID, chatbot_id: uuid.UUID, query_text: str) -> str:
        digest = hashlib.sha256(normalize_query_text(query_text).encode()).hexdigest()
        return f"{_KEY_PREFIX}:{organization_id}:{chatbot_id}:{digest}"

    async def get(
        self, organization_id: uuid.UUID, chatbot_id: uuid.UUID, query_text: str
    ) -> tuple[AnswerResponse, list[dict]] | None:
        if not settings.ENABLE_SEMANTIC_CACHE:
            return None
        raw = await self._redis.get(self._key(organization_id, chatbot_id, query_text))
        if raw is None:
            return None
        payload = json.loads(raw)
        answer = AnswerResponse.model_validate(payload["answer"])
        sources = [
            {**source, "chunk_id": uuid.UUID(source["chunk_id"]), "document_id": uuid.UUID(source["document_id"])}
            for source in payload["sources"]
        ]
        return answer, sources

    async def set(
        self,
        organization_id: uuid.UUID,
        chatbot_id: uuid.UUID,
        query_text: str,
        answer: AnswerResponse,
        sources: list[dict],
    ) -> None:
        if not settings.ENABLE_SEMANTIC_CACHE:
            return
        payload = {
            "answer": answer.model_dump(mode="json"),
            "sources": [
                {**source, "chunk_id": str(source["chunk_id"]), "document_id": str(source["document_id"])}
                for source in sources
            ],
        }
        await self._redis.set(
            self._key(organization_id, chatbot_id, query_text),
            json.dumps(payload),
            ex=settings.ANSWER_CACHE_TTL_SECONDS,
        )

    async def invalidate_organization(self, organization_id: uuid.UUID) -> None:
        """Called on document archive/delete (spec §57's "cached answers"
        must be removed on delete; archive is the same correctness concern
        one step earlier). Clears every cached answer for the org rather
        than trying to identify which specific cached queries touched the
        affected document — cache entries store the rendered answer, not
        which document(s) it drew from, and this org-wide sweep is cheap
        given the short TTL already bounds cache size.
        """
        pattern = f"{_KEY_PREFIX}:{organization_id}:*"
        async for key in self._redis.scan_iter(match=pattern):
            await self._redis.delete(key)
