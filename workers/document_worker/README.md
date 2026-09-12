# Document Worker

Celery worker responsible for asynchronous document processing (parsing, structuring, chunking, embedding).

Wired for queueing in **M2 — Document Upload + Storage** (Redis queue, job creation). **M3 — Generic Document Parsing** adds real Docling-based parsing. Regulatory structure induction (Pasal/Ayat/Huruf) and hierarchical chunking land in M4+.

See `docs/MASTER_DEVELOPMENT_SPEC.md` §59-60 (Background Processing, Worker Retry) and `docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md` (generic structure).

## M2: `verify_upload`

The one task implemented so far re-verifies an uploaded object's SHA-256 against the hash recorded at upload time (`app/tasks.py`). It is enqueued by `apps/api`'s `POST /documents/upload` via a producer-only Celery client (`apps/api/app/core/tasks.py`) that calls `send_task("document_worker.verify_upload", ...)` by name — see `docs/adr/ADR-016-knowledge-space-bootstrap-and-celery-producer-consumer-split.md`.

On a hash match, `verify_upload` chains directly into `parse_document.delay(job_id)` under the same job row (no new job/version row) — see M3 below.

## M3: `parse_document`

Runs the generic parsing pipeline (`app/parsing/`): Docling conversion with a cheap-first cascade (native text extraction -> layout/table refinement -> forced OCR, escalating only when a page-quality check fails), heuristic region segmentation, and generic document-tree building. Persists `document_regions`/`document_nodes` and sets `DocumentVersion.status` to `PARSED`, `REVIEW_REQUIRED` (OCR fallback was needed, or a page stayed unusable), or `PROCESSING_FAILED` (no pages / conversion raised).

Only the **generic** tree is built here — Pasal/Ayat/Huruf and any other specialized interpretation is M4 (see ADR-014 and the mixed-structure addendum). Known gap: Docling's OCR options are the only Level 3 fallback; true VLM-based hierarchy disambiguation (addendum §14) needs an LLM/VLM gateway that doesn't exist until M9.

`docling` is a heavy dependency (torch + OCR models) — first `uv sync` after pulling this change will be slow and download model weights.

This is a separate `uv` project from `apps/api` (own `pyproject.toml`/lockfile/venv) and does not import `apps/api`'s ORM models — `app/database.py` defines minimal Core `Table` objects for just the columns this worker touches. Keep those in sync by hand if the corresponding columns in `apps/api/app/documents/models.py` / `apps/api/app/ingestion/models.py` change.

### Running locally

```bash
cd workers/document_worker
uv sync
uv run celery -A app.celery_app worker --loglevel=info --pool=solo   # --pool=solo needed on Windows
```

Requires `docker compose up -d` (Postgres + Redis + MinIO) and `apps/api`'s migrations already applied (`uv run alembic upgrade head` from `apps/api`) — this worker reads a schema it doesn't own or migrate itself.

### LAN-M5/M6: budget reservation reconciliation

`document_worker.reconcile_stale_budget_reservations` recovers ingestion-budget reservations stranded `RESERVED` by a worker process killed mid-embedding (see `app/indexing/budget.py`'s `reconcile_stale_reservations`). It has a `beat_schedule` entry (every 15 minutes) in `app/celery_app.py`, but **only fires if a `celery beat` process is actually running** — this repo doesn't deploy one yet:

```bash
uv run celery -A app.celery_app beat --loglevel=info
```

Until beat is part of the deployment, run it manually or from an external scheduler:

```bash
uv run celery -A app.celery_app call document_worker.reconcile_stale_budget_reservations
```

### Tests

```bash
uv run pytest -v
```

Runs the task function directly (`verify_upload.run(...)`, not via a live broker) against real Postgres + MinIO from Docker Compose.
