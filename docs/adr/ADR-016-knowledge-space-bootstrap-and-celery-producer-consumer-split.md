# ADR-016: Knowledge Space Auto-Bootstrap, and a Producer-Only Celery Client in the API

## Context

Milestone M2 (§98: upload, SHA-256, object storage, processing jobs, queue, status UI) needs to persist `Document` rows, but the ERD (§51) models `KNOWLEDGE_SPACE ||--o{ DOCUMENT : groups` with the same mandatory-one-side cardinality as `ORGANIZATION ||--o{ DOCUMENT : owns` — a relationship we already treat as non-nullable because tenant isolation is a hard security boundary (§7). M2's own bullet list never mentions knowledge spaces, but the FK can't be satisfied without at least one existing per organization.

Separately, M2 needs a background queue (§59: `POST upload → job_id → queued → processing`) and a worker (§60: retry semantics). `workers/document_worker/` exists only as a placeholder README — no Celery app, no task code, and it is a separate `uv` project from `apps/api` with no shared Python package between them.

## Decision

- **KnowledgeSpace gets minimal CRUD in M2** (`app/knowledge/`: create/list/get/delete), and `POST /auth/register` (M1) is extended to auto-create one default `KnowledgeSpace` named "General" for every newly bootstrapped organization, in the same transaction as the Organization/User/OrganizationMember rows.
- **The FastAPI app holds a producer-only Celery client** (`app/core/tasks.py`): `Celery(broker=settings.REDIS_URL)` with no task modules imported, calling `.send_task("document_worker.verify_upload", args=[...])` by name. The actual task implementation lives entirely in `workers/document_worker`, which gets its own `pyproject.toml` and runs as an independent `uv run celery -A app.celery_app worker` process.
- The worker is **not** added as a new Docker Compose service; it runs as a native local-dev process, matching ADR-013's "infra-only Docker Compose" scope (Postgres/Redis/Qdrant/MinIO only).

## Alternatives

- Making `knowledge_space_id` nullable on `Document` to avoid building KnowledgeSpace CRUD this milestone — rejected; it contradicts the ERD's own cardinality notation and would need a follow-up migration to tighten later, plus it blocks the natural "which space does this go in" step in the upload UI (§69's modal doesn't need to ask if there's always a sensible default, but the field still has to exist).
- Requiring the user to manually create a KnowledgeSpace before their first upload — rejected; every new organization has to be able to exercise M2 immediately, and the spec gives no indication that space creation is meant to gate uploading.
- Sharing a Python package between `apps/api` and `workers/document_worker` (e.g., a new `packages/` Python library for models/config) — rejected for this milestone; the repo's `packages/*` convention is pnpm-workspace (JS/TS) scoped, no cross-app Python sharing mechanism exists yet, and introducing one is a bigger structural change than this milestone's scope justifies. Revisit if duplicated model/config drift becomes a real maintenance problem.
- Having `apps/api` import `workers/document_worker`'s task module directly instead of `send_task` by name — rejected; it would force the API process to install the worker's dependencies (and vice versa is not even possible, since they're separate `uv` projects), defeating the point of having them as separate deployables.
- Running the Celery worker as a new Docker Compose service now — rejected; ADR-013 deliberately scoped Compose to infrastructure only so app-process iteration stays fast via native hot-reload/restart; containerizing the worker is a deployment-packaging concern for M15, same reasoning ADR-013 already gives for `apps/api`/`apps/web`.

## Reasons

- Auto-creating a default space keeps M2 usable end-to-end (upload actually works right after registration) without inventing product behavior the spec doesn't describe (no "onboarding wizard" is specified — a sensible default is the minimal viable choice).
- `send_task` by name is Celery's own recommended pattern for producer/consumer separation and avoids coupling two independently-versioned `uv` projects.

## Consequences

- Every organization gets exactly one "General" knowledge space automatically; multi-space organization (the §8 example: Pendidikan/Kepegawaian/Regulasi/SOP/...) is fully supported by the CRUD endpoints added here, just not auto-populated beyond the one default.
- If `workers/document_worker`'s task name or argument shape ever changes, `app/core/tasks.py`'s `send_task` call must be updated in lockstep by hand — there is no type-checked contract between producer and consumer. Acceptable for now given the small surface (one task); worth revisiting (e.g., a shared task-signature contract) if the number of tasks grows.
- Running the worker natively means local development requires a third long-running process (API, web, worker) in addition to Docker Compose's infra containers — documented in `workers/document_worker/README.md`.
- The worker accesses Postgres via hand-written SQLAlchemy Core `Table` objects covering only the columns it touches (`document_versions`, `processing_jobs`), not `apps/api`'s ORM models — confirms the drift risk above is real, not hypothetical; any column rename/type change in `apps/api/app/documents/models.py` or `apps/api/app/ingestion/models.py` must be mirrored by hand in `workers/document_worker/app/database.py`.
- The worker's engine uses SQLAlchemy's `NullPool` rather than the pooled engine `apps/api` uses: each Celery task invocation runs its own `asyncio.run()`, creating and tearing down a fresh event loop per task, and a connection pooled from one loop is unusable once that loop closes (confirmed live — the first task on a worker process succeeded, every task after it failed with "Event loop is closed" until this was applied). This trades away connection reuse for correctness; acceptable given this task's low volume and short runtime.

## Status

Accepted.
