# ADR-018: Cross-Process Answer-Cache Invalidation on Document Version ACTIVE

## Context

ADR-017 introduced `AnswerCacheService` and accepted a known gap: a document
version reaching ACTIVE (fresh publish or M13 auto-supersede) does not
invalidate cached answers, because that transition happens inside
`workers/document_worker` — a separate Python process with its own venv and
no import path to apps/api's `app.caching.answer_cache` module. ADR-017 left
`ANSWER_CACHE_TTL_SECONDS` (default 600s) as the sole bound on staleness for
that path, and named cross-process Redis pub/sub as the eventual fix but
deferred it as more infrastructure than M15's scope called for.

That gap is a real correctness risk: within the TTL window, a user can
receive a cached answer built from evidence in a regulation version that has
since been superseded — the exact failure mode the project's evidence-first
principle exists to prevent.

## Decision

Rather than pub/sub with a background subscriber in apps/api (ADR-017's
"cleaner long-term fix"), the worker invalidates directly: both processes
already share one Redis instance (it's already the Celery broker/backend for
the worker, and the config already carries `REDIS_URL`). A new module,
`workers/document_worker/app/caching.py`, mirrors
`AnswerCacheService`'s own key schema — `answer_cache:{organization_id}:*` —
and performs the identical scan+delete `AnswerCacheService.
invalidate_organization()` does, without importing it.

`_index_document_async` (in `workers/document_worker/app/tasks.py`) calls
`invalidate_answer_cache(organization_id)` once, after its transaction
(including M13 auto-supersede bookkeeping) commits — covering both a fresh
publish and a supersede in the same call, since both leave exactly one
version ACTIVE per document. The call is wrapped to catch and log any
exception rather than propagate: a Redis hiccup here must not fail an
otherwise-successful indexing job. If it fails, `ANSWER_CACHE_TTL_SECONDS`
is still the fallback bound, same as before this change.

## Alternatives

- **Redis pub/sub + apps/api subscriber** (ADR-017's original suggestion):
  rejected as unnecessary complexity — a direct scan+delete against a
  Redis instance the worker can already reach does the same job without a
  new channel or a long-running subscriber task to keep alive.
- **Shared package for the cache key schema**: rejected — apps/api and the
  worker are separate installable projects with separate dependency sets;
  extracting a shared package for one function is more machinery than the
  duplication it would remove. The two copies are small and now
  cross-referenced in comments on both sides.
- **Leave the gap as TTL-only**: rejected — this is exactly the kind of
  correctness gap the project's priority order (CLAUDE.md §102) puts ahead
  of latency/cost concerns; a 600s window of stale legal answers is not an
  acceptable steady-state behavior once a low-cost fix is available.

## Consequences

- The worker now depends on `redis` for one more purpose beyond the Celery
  broker/backend (it already had the dependency) and gains a small pooled
  client at `workers/document_worker/app/core/redis_client.py`, mirroring
  apps/api's own.
- The two projects now share an implicit contract on the answer-cache Redis
  key format. A future change to that schema in
  `apps/api/app/caching/answer_cache.py` must be mirrored in
  `workers/document_worker/app/caching.py`, or this invalidation silently
  stops matching any key. Both files cross-reference each other in comments
  to make this visible.
- `access_scope`/`knowledge_base_version` key ingredients remain out of
  scope, per ADR-017 — this ADR only closes the ACTIVE-transition
  invalidation gap, not the other scope decisions ADR-017 made.

## Status

Accepted.
