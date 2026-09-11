# LAN Archive Progress

Checkpoint doc for the LAN archive ingestion track (`docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`). Updated at the end of each milestone so the next session can resume without re-auditing from scratch.

## LAN-M2: Selective snapshot and incremental sync — **complete**

### Acceptance criteria status

| Criterion | Status |
|---|---|
| Promotion creates Document/DocumentVersion/ProcessingJob and enqueues the existing `verify_upload` | **Passed** — `test_promotion_creates_document_version_and_enqueues_verify_upload` |
| Duplicate-content promotion links to the existing version, no new storage write | **Passed** — `test_duplicate_content_links_to_existing_version_without_new_storage_write` |
| Unsupported extension (e.g. legacy `.doc`) fails cleanly without staging | **Passed** — `test_unsupported_extension_fails_without_staging` |
| Disk watermark pauses (not fails) and is retryable | **Passed** — `test_disk_watermark_pauses_rather_than_fails` |
| A crashed worker's stale lease is reclaimed by a later attempt | **Passed** — `test_stale_lease_is_reclaimed_by_a_later_attempt` |
| File-stability check (two independent stats) works and detects changes | **Passed** — `test_check_file_stable_*` (test_promotion.py) |
| Streaming staging computes correct hash/size without loading the whole file eagerly beforehand | **Passed** — `test_stage_to_temp_file_computes_correct_hash_and_size` |
| Oversized file during staging is rejected and cleaned up | **Passed** — `test_stage_to_temp_file_raises_and_cleans_up_when_too_large` |
| No regression in existing suites (LAN-M1 + M0-M15 core) | **Passed** — see Test commands and results below |

### Key design decision confirmed during implementation

Promotion reuses the **existing** `apps/api/app/ingestion/router.py::_create_version_and_job` shape exactly (Document → DocumentVersion(UPLOADED) → ProcessingJob(QUEUED) → enqueue `verify_upload`) rather than building a parallel pipeline. M3-M6 (parse/interpret/chunk/index) needed **zero changes** — confirmed by the fact that a promoted PDF flows into the same `verify_upload` task the HTTP upload path already uses and is fully unit-testable without touching that pipeline at all.

### Gap found and fixed during this milestone (not caught in planning)

`SourceRoot` had no `knowledge_space_id` in LAN-M1 — but `Document.knowledge_space_id` is `NOT NULL`, so promotion had nowhere to put a new Document. Added `source_roots.knowledge_space_id` (required at creation, validated against the same org) via this milestone's migration. Recorded here rather than silently folded into "LAN-M1 was already correct" — it wasn't; LAN-M1's `CreateSourceRequest`/tests needed updating too (`apps/api/tests/unit/test_sources_rbac.py`).

### Files changed

**Docs:**
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)

**apps/api:**
- `apps/api/app/sources/models.py` — added `PromotionRecord`/`PromotionStatus`, added `SourceRoot.knowledge_space_id`
- `apps/api/app/sources/schemas.py` — added promotion request/response schemas, `knowledge_space_id`, `promotion_status`
- `apps/api/app/sources/router.py` — added `POST /sources/{id}/entries/promote`, `knowledge_space_id` validation, `promotion_status` in entries listing
- `apps/api/app/documents/models.py` — added `DocumentVersion.source_entry_id` (nullable, NULL for ordinary uploads)
- `apps/api/app/core/tasks.py` — added `enqueue_promote_source_entry`
- `apps/api/alembic/versions/a7057580f523_add_lan_archive_promotion_records.py` — new migration
- `apps/api/tests/unit/test_sources_rbac.py` — updated for `knowledge_space_id` requirement

**workers/document_worker:**
- `workers/document_worker/app/sources/adapter.py` — added `stat()`/real `open_stream()` to the `Protocol`
- `workers/document_worker/app/sources/local_fake_adapter.py`, `windows_unc_adapter.py` — implemented `stat()`/`open_stream()`
- `workers/document_worker/app/sources/promotion.py` — new: staging/hashing/stability/dedup/watermark helpers
- `workers/document_worker/app/sources_tasks.py` — added `promote_source_entry` task, lease-claim logic
- `workers/document_worker/app/storage.py` — added `put_object_stream`, `build_original_object_key` (worker's first write path to object storage)
- `workers/document_worker/app/database.py` — added `promotion_records` mirror; extended `documents`/`document_versions`/`source_roots` mirrors with columns needed for INSERT
- `workers/document_worker/app/core/config.py` — added `SCAN_STABILITY_WINDOW_SECONDS` (missed in LAN-M1 — worker actually needs it, apps/api's copy was never load-bearing), `STAGING_DIR`, `MIN_FREE_DISK_MB`, `PROMOTION_LEASE_SECONDS`
- `workers/document_worker/tests/test_promotion.py` — new, 13 pure unit tests
- `workers/document_worker/tests/test_sources_tasks.py` — added 5 promotion integration tests, updated fixtures for `knowledge_space_id`

### Bugs caught and fixed during implementation (not just at the end)

1. Worker's `source_roots` Core Table mirror omitted `source_type` — the promotion task needs to *read* it to pick an adapter (LAN-M1 only ever needed to *write* health, so this was missed). Fixed by adding the column to the mirror.
2. Real circular import: `sources_tasks.py` importing `from app.tasks import verify_upload` at module level broke whenever `app.tasks` was the first module imported (e.g. a test importing directly from it) — `app.tasks` imports `app.celery_app`, which imports `sources_tasks`, which needs `app.tasks` back before it's finished loading. Fixed with a lazy (in-function) import. Verified against **both** import orders after the fix.
3. `SCAN_STABILITY_WINDOW_SECONDS` was defined in LAN-M1 only on apps/api's config (marked "unused until LAN-M2") — but the worker is what actually needed it, and it was never added there. Caught by an `AttributeError` at test time, not by inspection.

### Migrations

`a7057580f523_add_lan_archive_promotion_records.py` — additive: new `promotion_records` table, new `lan_promotion_status` enum, new nullable `document_versions.source_entry_id` column (+FK), new required `source_roots.knowledge_space_id` column (+FK) — safe because `source_roots` had zero rows at migration time (verified before writing the migration). No existing table's existing columns touched. Applied successfully (`0faff961e56e` → `a7057580f523`).

### Test commands and results

```
cd apps/api && uv run pytest -q
  -> 203 passed (unchanged from LAN-M1 — this milestone's apps/api changes
     are schema/router additions, covered by the updated RBAC test file)

cd workers/document_worker && uv run pytest -q --ignore=tests/test_parse_document.py \
  --ignore=tests/test_pipeline.py --ignore=tests/test_region_segmenter.py --ignore=tests/test_tree_builder.py
  -> 107 passed, 1 skipped (was 89 passed, 1 skipped after LAN-M1; +13 test_promotion.py
     + 5 new promote_source_entry integration tests)

cd workers/document_worker && uv run pytest tests/test_parse_document.py tests/test_pipeline.py \
  tests/test_region_segmenter.py tests/test_tree_builder.py -q
  -> 18 passed (same known-harmless "Windows fatal exception: access violation"
     noise from docling_parse's internal timing thread, per windows-toolchain-
     quirks memory — did not fail the run)
```

Test speed note: the real file-stability check sleeps `SCAN_STABILITY_WINDOW_SECONDS`
between its two stats (30s default) — an autouse fixture in
`test_sources_tasks.py` patches this to 0 for the DB-integration tests (real
timing is covered separately, fast, in `test_promotion.py`'s own
`check_file_stable` tests). Without that fixture the suite took 2:43 instead
of 43s for no additional coverage.

### Assumptions not yet validated

- Everything already listed under LAN-M1 (production OS/deployment shape, real Windows LAN/SMB topology) still applies — promotion via `WindowsUNCAdapter` is exercised only through the shared `_filesystem_walk`/adapter code paths that `LocalFakeAdapter` already covers, never a real share.
- The blocking-sleep file-stability check (`time.sleep` inside the Celery task, not a two-phase scheduled follow-up) is a known, documented scalability trade-off — fine for pilot-scale promotion volume, holds a worker slot for the stability window otherwise. Revisit if a pilot needs higher promotion throughput.
- Missing-file detection (carried over from LAN-M1) is still not implemented — still requires a grace-period policy decision before it's built.

### Blockers

- Same as LAN-M1: no real Windows LAN/SMB share reachable from this dev environment.

### Next step

LAN-M2 is complete per its acceptance criteria. Per Operating Rule #3, **do not** proceed to LAN-M3 (PDF/Word parsing, versioned index) automatically — re-read this file plus the implementation plan's LAN-M3 section first.

## Milestone history

- **LAN-M2** — selective snapshot/promotion into the existing document pipeline, streaming transfer, dedup, disk watermark, crash-safe lease-based idempotency. See acceptance criteria table above.
- **LAN-M1** — source registry, adapter contract, catalog-only discovery. 9/9 acceptance criteria passed; `WindowsUNCAdapter` implemented but real-UNC validation still pending client environment access.
