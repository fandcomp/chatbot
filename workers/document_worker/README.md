# Document Worker

Celery worker responsible for asynchronous document processing (parsing, structuring, chunking, embedding).

Wired for queueing in **M2 — Document Upload + Storage** (Redis queue, job creation). Real processing tasks (Docling parsing, regulatory structure induction, hierarchical chunking) land starting **M3 — Generic Document Parsing**.

See `docs/MASTER_DEVELOPMENT_SPEC.md` §59-60 (Background Processing, Worker Retry).

## M2: `verify_upload`

The one task implemented so far re-verifies an uploaded object's SHA-256 against the hash recorded at upload time (`app/tasks.py`). It is enqueued by `apps/api`'s `POST /documents/upload` via a producer-only Celery client (`apps/api/app/core/tasks.py`) that calls `send_task("document_worker.verify_upload", ...)` by name — see `docs/adr/ADR-016-knowledge-space-bootstrap-and-celery-producer-consumer-split.md`.

This is a separate `uv` project from `apps/api` (own `pyproject.toml`/lockfile/venv) and does not import `apps/api`'s ORM models — `app/database.py` defines minimal Core `Table` objects for just the columns this worker touches. Keep those in sync by hand if the corresponding columns in `apps/api/app/documents/models.py` / `apps/api/app/ingestion/models.py` change.

### Running locally

```bash
cd workers/document_worker
uv sync
uv run celery -A app.celery_app worker --loglevel=info --pool=solo   # --pool=solo needed on Windows
```

Requires `docker compose up -d` (Postgres + Redis + MinIO) and `apps/api`'s migrations already applied (`uv run alembic upgrade head` from `apps/api`) — this worker reads a schema it doesn't own or migrate itself.

### Tests

```bash
uv run pytest -v
```

Runs the task function directly (`verify_upload.run(...)`, not via a live broker) against real Postgres + MinIO from Docker Compose.
