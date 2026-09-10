# LAN Archive Progress

Checkpoint doc for the LAN archive ingestion track (`docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`). Updated at the end of each milestone so the next session can resume without re-auditing from scratch.

## LAN-M1: Audit, source foundation, catalog without AI cost — **complete**

### Acceptance criteria status

| # | Criterion | Status |
|---|---|---|
| 1 | Migration applies cleanly | **Passed** — `alembic upgrade head` (revision `0faff961e56e`) applied cleanly on the dev DB, no changes to existing tables |
| 2 | Local-fake source scan produces correct entries via admin API | **Passed** — `test_sources_rbac.py`, `test_sources_tasks.py` |
| 3 | Offline source doesn't mark entries missing | **Passed** — `test_offline_source_does_not_touch_existing_entries` |
| 4 | Partial subtree failure doesn't poison rest of scan | **Passed** — `test_one_inaccessible_subtree_does_not_poison_the_rest` |
| 5 | Re-scan with no changes is a no-op (no new entries) | **Passed** — `test_rescan_with_no_changes_creates_no_new_entries` |
| 6 | Discovery never calls provider/storage APIs | **Passed** — `test_catalog_only_scan_produces_entries_and_touches_no_provider` asserts `get_object_bytes` raises if called; also true by code inspection (no Docling/embedding/LLM/storage import in `sources_tasks.py` or `sources/` package) |
| 7 | New endpoints tenant-scoped and role-gated | **Passed** — `test_sources_rbac.py` (6 tests: create requires OWNER/ADMIN, viewer can list but not scan, cross-org access is 404) |
| 8 | No regression in existing suites | **Passed** — see Test commands and results below |
| 9 | WindowsUNCAdapter exists, tested locally (not against real UNC) | **Implemented**, exercised only indirectly (shares `_filesystem_walk.py` with `LocalFakeAdapter`, which is directly tested) — **real-UNC validation explicitly pending**, see Blockers |

### Files changed

**Docs (new):**
- `docs/adr/ADR-020-lan-archive-source-connector.md`
- `docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md`
- `docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)
- `docs/operations/LAN_CONNECTOR_RUNBOOK.md`
- `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md` (stub, LAN-M6)
- `CLAUDE.md` (pointer section added)

**apps/api (new):**
- `apps/api/app/sources/{__init__,models,schemas,router}.py`
- `apps/api/tests/unit/test_sources_rbac.py`
- `apps/api/alembic/versions/0faff961e56e_add_lan_archive_source_registry.py`

**apps/api (modified):**
- `apps/api/app/core/config.py` — `MAX_FILE_SIZE_MB` 50→100 (documented as per-file), added `CONNECTOR_ENABLED`/`CONNECTOR_ALLOWED_HOSTS`/`SCAN_PAGE_SIZE`/`SCAN_STABILITY_WINDOW_SECONDS`
- `apps/api/app/core/tasks.py` — added `enqueue_scan_source`
- `apps/api/app/main.py` — registered `sources_router`
- `apps/api/alembic/env.py` — imports new models for autogenerate
- `.env.example` — new connector config vars documented as pilot defaults

**workers/document_worker (new):**
- `workers/document_worker/app/sources/{__init__,adapter,_filesystem_walk,local_fake_adapter,windows_unc_adapter,discovery}.py`
- `workers/document_worker/app/sources_tasks.py`
- `workers/document_worker/tests/test_sources_walk.py`
- `workers/document_worker/tests/test_sources_tasks.py`

**workers/document_worker (modified):**
- `workers/document_worker/app/database.py` — added `source_roots`/`scan_runs`/`source_entries` Core Table mirrors
- `workers/document_worker/app/celery_app.py` — registers `sources_tasks`
- `workers/document_worker/app/core/config.py` — added `CONNECTOR_ALLOWED_HOSTS`/`SCAN_PAGE_SIZE`

### Migrations

`0faff961e56e_add_lan_archive_source_registry.py` — additive only, adds `source_roots`, `scan_runs`, `source_entries` tables plus 5 new Postgres enum types (`lan_source_type`, `lan_source_health`, `lan_scan_run_status`, `lan_discovery_status`, `lan_entry_access_status`). No existing table touched. Applied successfully against the dev DB (`alembic upgrade head`, `d8a8dfc7497c` → `0faff961e56e`).

### Test commands and results

```
cd apps/api && uv run pytest -q
  -> 203 passed (was 197 before this milestone; +6 new RBAC tests)

cd workers/document_worker && uv run pytest -q --ignore=tests/test_parse_document.py \
  --ignore=tests/test_pipeline.py --ignore=tests/test_region_segmenter.py --ignore=tests/test_tree_builder.py
  -> 89 passed, 1 skipped (was 80 passed, 1 skipped before; +9 new LAN-M1 tests)
  (the 1 skip is a pre-existing symlink-creation-permission skip, unrelated —
   also hit by this milestone's own symlink-traversal test on this machine)

cd workers/document_worker && uv run pytest tests/test_parse_document.py tests/test_pipeline.py \
  tests/test_region_segmenter.py tests/test_tree_builder.py -q
  -> 18 passed, 27 warnings in 324.70s — run separately per this repo's own
     documented Docling-suite segfault-risk note (memory: windows-toolchain-
     quirks); no segfault this run, clean pass. Untouched by this milestone's
     changes (LAN-M1 never modifies parsing code), run purely as a
     regression check.
```

### Assumptions not yet validated

- Production OS/deployment shape for `workers/document_worker` is unknown — ADR-020's choice of `WindowsUNCAdapter` assumes the worker keeps running natively on Windows, matching today's actual deployment (confirmed via ADR-016 and this session's own tooling). If production ever containerizes the worker on Linux, ADR-020 must be revisited.
- Real Windows LAN/SMB topology, credentials, and scale are all "belum diketahui" per the client info table in `PROMPT_CLAUDE_CODE_UPDATE_CHATBOT_4TB.md` — LAN-M1 is validated only against `LocalFakeAdapter`/a real local filesystem, never a real share.
- Missing-file detection (`MISSING_CANDIDATE`/`CONFIRMED_MISSING` transitions) is deliberately **not implemented** in LAN-M1 — `SourceEntry.discovery_status` is only ever set to `PRESENT` today. The addendum's grace-period policy for confirming a file gone needs a decision before this is built; scoped explicitly out of LAN-M1's 9 acceptance criteria.

### Blockers

- No real Windows LAN/SMB share reachable from this dev environment — `WindowsUNCAdapter` cannot be field-validated until client provides access. Tracked in `docs/operations/LAN_CONNECTOR_RUNBOOK.md`.

### Next step

LAN-M1 is complete per its acceptance criteria. Per Operating Rule #3 (one milestone at a time), **do not** proceed to LAN-M2 automatically — the next session should re-read this file plus `docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`'s LAN-M2 section before starting selective-snapshot/incremental-sync work.

## Milestone history

- **LAN-M1** (this session) — source registry, adapter contract, catalog-only discovery. See acceptance criteria table above.
