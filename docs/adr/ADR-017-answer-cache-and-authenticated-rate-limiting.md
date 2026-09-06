# ADR-017: Answer Cache Scope and Authenticated Rate-Limit Keying

## Context

M15 (Production Hardening, spec §98) targets security, performance, caching,
backup, monitoring, rate limits, evaluation, and load test — deliberately
scoped down (per user direction) to: rate-limiting the two LLM-cost chat
endpoints, a validated-answer cache (spec §45, §47 rule 9), a
prompt-injection hardening pass on the context builder, a RAG evaluation
harness (spec §96), and backup/load-test tooling. Two of these — the answer
cache and rate-limit keying — involve real design decisions not fully
specified by the spec, and are recorded here per CLAUDE.md's "no
architecture change without an ADR" rule.

### Rate limiting

Before M15, `slowapi`'s `Limiter` (keyed by `get_remote_address`, i.e. pure
IP) covered only `/auth/register`, `/auth/login` (5/minute), and the two
upload endpoints (20/minute). `/chat`, `/chat/stream`, and
`/knowledge/test` — the endpoints that actually trigger a paid LLM call —
had zero rate limiting. Spec §95 asks for limiting "berdasarkan: tenant,
user, IP, endpoint" and notes upload and chat need different policies.

### Answer cache

Spec §45 specifies a cache key of `tenant_id, chatbot_id,
knowledge_base_version, access_scope, semantic_query_signature` and
invalidation "jika document version berubah, KB version berubah, permission
berubah, document archived/deleted." Two of those five key ingredients and
two of the four invalidation triggers reference concepts this codebase does
not have yet:

- `KnowledgeBaseVersion` is explicitly deferred (see M13's own scope note in
  the README) — there is no KB-version counter to key on or invalidate by.
- `access_scope` narrower than `organization_id` does not exist — every org
  member can query every knowledge space they belong to; there is no
  per-user document-level ACL.
- "document version berubah" / "KB version berubah" both describe a
  document reaching a new ACTIVE version, which happens in
  `workers/document_worker` (a separate Python process with its own venv,
  no import path to apps/api's cache module) via M13's auto-supersede path
  or a fresh publish.

## Decision

**Rate limiting**: add `user_or_ip_key(request)` (`app/auth/router.py`) —
decodes the existing session JWT's `sub` claim (already issued for
authentication, no token-format change needed) and keys by `user:{user_id}`
when present, falling back to IP. Applied via
`@limiter.limit(N, key_func=user_or_ip_key)` to `/chat`, `/chat/stream`
(30/minute) and `/knowledge/test` (20/minute, matching the existing upload
budget since it's also an admin/preview action). This key function is
**never** used for authorization — `require_role`'s DB-backed membership
lookup still runs unchanged on every request; the JWT decode here only
selects a rate-limit bucket.

Tenant-level (org-wide combined) limiting is deferred: achieving it
synchronously would need either an `organization_id` JWT claim (a token
schema change, non-trivial to roll out against already-issued sessions) or
a DB round-trip inside the rate-limit check (adds latency to every request
specifically to decide whether to reject it). User-level keying already
closes the most urgent gap — a shared office IP no longer means all its
users share one 30/minute budget — without either cost.

**Answer cache** (`app/caching/answer_cache.py`): exact-normalized-query
match, not embedding-similarity semantic matching — spec §104 explicitly
defers "advanced caching" post-MVP, and an exact match already serves the
common repeated-FAQ case this cache targets. Key: `organization_id`,
`chatbot_id`, and a SHA-256 of the normalized query text —
`knowledge_base_version` and `access_scope` are omitted for the reasons
above.

Three scope restrictions bound correctness without those two key
ingredients:

1. **First-turn only.** `ChatService.answer()` only consults the cache when
   `conversation_context is None` (a brand-new conversation). A cache key
   built from query text alone cannot represent prior conversation turns, so
   serving a cache hit to a follow-up question risks answering the wrong
   thing.
2. **Org-wide queries only**, not knowledge-space-scoped ones
   (`knowledge_space_id is None`). A scoped query's answer could differ from
   an org-wide query with identical text; the key doesn't carry
   `knowledge_space_id`, so scoped queries skip the cache entirely rather
   than risk a cross-scope hit.
3. **Validated answers only** (`insufficient_evidence is False`) — matches
   §45's "Cache hanya untuk validated answer" directly.

**Invalidation**: `AnswerCacheService.invalidate_organization()` is called
from the two document-lifecycle events apps/api can reach synchronously —
`POST /documents/{id}/archive` and `DELETE /documents/{id}` — clearing every
cached answer for the organization (cache entries don't record which
document(s) they drew from, and an org-wide sweep is cheap given the short
TTL already bounds how much accumulates). **A new document version reaching
ACTIVE (including M13's auto-supersede) is not covered** — that transition
happens in the worker process, which has no connection to this cache.
`ANSWER_CACHE_TTL_SECONDS` (default 600s) is the sole bound on staleness for
that path. This is an accepted v1 gap, not a hidden one.

## Alternatives

- **Full KnowledgeBaseVersion-keyed cache**: rejected for now — would
  require building KB versioning first (already deferred, its own separate
  scope per M13), not something to smuggle in as a side effect of adding
  caching.
- **Cross-process invalidation via Redis pub/sub** (worker publishes an
  "org X documents changed" event on every ACTIVE transition, apps/api
  subscribes and bumps a per-org cache generation counter): the cleaner
  long-term fix for the worker-side gap above, but a new pub/sub channel and
  a background subscriber task in apps/api is more infrastructure than this
  milestone's scope calls for. Revisit if the TTL-only bound proves too
  loose in practice.
- **Embedding-similarity semantic cache**: rejected — spec §104 explicitly
  places "advanced caching" post-MVP; building a second small vector index
  just for cache-key matching duplicates M6's own Qdrant-backed indexing
  infrastructure for a case exact-match already covers reasonably well.
- **Tenant + user + IP combined rate-limit key**: rejected for v1 in favor
  of user-only — see "Tenant-level ... is deferred" above.

## Consequences

- A cached answer's own `structured_answer` JSONB field on the replayed
  `Message` row is the previously-computed `AnswerResponse`, not a fresh
  `StructuredAnswer` from the LLM — already documented as safe in
  `chat/models.py`'s own comment ("for a future UI needing raw structure",
  currently unused elsewhere).
- `QueryLog.cache_hit` (new column, migration `3ff190daf6b8`) and
  `AnalyticsOverview.cache_hit_rate` make the cache's effectiveness visible
  in the M14 dashboard without needing a separate observability surface.
- A follow-up question rephrasing the same first question in different
  words never hits the cache (exact-match only) — accepted, per the
  "not advanced caching" scope above.
- If per-user knowledge-space ACLs are ever introduced, this cache's key
  MUST be revisited to add `access_scope` — serving one user's cached
  answer to another user who lacks access to the same knowledge space would
  be a real data leak at that point (not today, since no such ACL exists).

## Status

Accepted.
