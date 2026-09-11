# LAN Archive Progress

Checkpoint doc for the LAN archive ingestion track (`docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md`). Updated at the end of each milestone so the next session can resume without re-auditing from scratch.

## LAN-M6: Pilot and operations guide — **partial, blocked on real client access**

LAN-M6 depends on "a working LAN-M1..LAN-M5 pipeline **and client-provided access/credentials**" (implementation plan). The pipeline dependency is now satisfied (LAN-M1-M5 complete); the client-access dependency is not — no real Windows LAN/SMB share has ever been reachable from this dev environment, same blocker every prior milestone recorded.

Scoped per an explicit decision with the user: write the deliverables that don't need real client data now (backup/restore procedures, rollback plan, staged production rollout guidance); leave sampling, real LAN throughput benchmarks, cost projection, and retrieval evaluation on real regulations explicitly blocked rather than faked with synthetic numbers presented as a pilot.

### What was delivered

- `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md` — filled in (was a stub): backup/restore procedures per store (Postgres/MinIO/Qdrant/embedding cache/Redis, with which stores are derivable vs. not), a three-granularity rollback plan (document version / migration / crashed job), and a 5-phase staged rollout guide (dry-run discovery → small controlled promotion → budget-gated pilot scale → retrieval/access validation → full rollout) with exit criteria and rollback triggers per phase. The still-blocked items (sampling, benchmarks, cost projection, retrieval eval) remain explicitly recorded as blocked, not attempted.
- `docs/operations/LAN_CONNECTOR_RUNBOOK.md` — added a pointer to the pilot plan (it was LAN-M1-scoped only and never updated for M2-M5) and documented a real gap found while writing this: **no endpoint exists to disable/delete a `SourceRoot`** once registered (`apps/api/app/sources/router.py` has create/list/scan/entries/promote, nothing to stop a misconfigured source). Recorded as a pre-flight check for Phase 0 of rollout, not silently assumed to exist.

### Gap found while writing the rollout guidance (not caught in planning)

Reservation/settlement (LAN-M5's `budget.py`) has no automatic recovery if a worker process is lost (not just a retried task) between `reserve_ingestion_budget` and `settle_usage`/`release_reservation` — the `usage_ledger_entries` row stays `RESERVED` indefinitely, permanently shrinking that org's budget headroom by the reserved amount. Celery's task-level retry doesn't cover a genuinely killed worker process. Recorded in the pilot plan's backup/restore section as a recommended periodic-reconciliation job before relying on the budget gate at real production volume — not built this pass, since it surfaced while documenting operational procedures, not while implementing LAN-M5 itself.

### Files changed

**Docs only — no code this pass:**
- `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md` — filled in per above
- `docs/operations/LAN_CONNECTOR_RUNBOOK.md` — cross-reference + known-limitation addition
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)

### Explicitly deferred / blocked (recorded, not silently dropped)

- **Representative sampling** (300-500 documents), **cost projection**, **real benchmarks** (OCR/embedding throughput, LAN transfer rate, chat latency idle-vs-active), **retrieval evaluation on real Indonesian regulatory queries** — all need real client access/data this environment doesn't have. See `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md`'s "Blocked pending real client access/credentials" section.
- **Automatic reconciliation for stranded `RESERVED` budget entries** — found and recorded above, not built.
- **A `SourceRoot` disable/delete endpoint** — found and recorded above, not built (pre-existing gap since LAN-M1, only surfaced now while writing operational guidance).

### Blockers

- No real Windows LAN/SMB share reachable from this dev environment — same as every prior milestone. This is the actual, sole blocker on LAN-M6's remaining scope; nothing else is pending.

### Next step

LAN-M6's access-independent deliverables are complete. Its remaining scope (sampling, benchmarking, retrieval eval, cost projection) cannot proceed without client-provided LAN/SMB access and credentials — this is an external dependency, not an engineering task to pick up next. When real access becomes available: re-read `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md`'s "Blocked" section and execute Phase 0 of the rollout guidance first (dry-run discovery), not a full sample promotion.

## LAN-M5: Ingestion budget control — **complete**

Scoped to **backend cost control only, admin UI deferred** (a deliberate decision, confirmed before starting): `git log` confirmed no LAN-facing frontend exists yet for any milestone, so "admin UI" would be a brand-new surface, meaningfully separable from the part that actually prevents uncontrolled spend. This milestone builds the usage ledger, versioned pricing config, and an atomic admission-control gate in front of the only currently-paid ingestion call.

### Acceptance criteria status

| Criterion | Status |
|---|---|
| A reservation succeeds and increments `reserved_usd` correctly within budget | **Passed** — `test_reserve_ingestion_budget_succeeds_within_limit` |
| A reservation over the limit raises, never silently proceeds | **Passed** — `test_reserve_ingestion_budget_raises_when_over_the_limit` |
| An unknown price is never treated as free | **Passed** — `test_reserve_ingestion_budget_never_treats_an_unknown_price_as_free` |
| Settlement moves `reserved_usd` → `spent_usd` at the reserved amount | **Passed** — `test_settle_usage_moves_reserved_to_spent` |
| Release gives back `reserved_usd` without ever charging `spent_usd` | **Passed** — `test_release_reservation_gives_back_reserved_without_charging_spent` |
| Concurrent reservations near the ceiling never oversubscribe | **Passed** — `test_concurrent_reservations_near_the_ceiling_never_oversubscribe` |
| Pricing lookup excludes an expired rate | **Passed** — `test_get_current_rate_excludes_an_expired_rate` |
| A job whose estimated cost exceeds budget pauses (`PAUSED_BUDGET`) and retries, never fails outright, never calls Voyage | **Passed** — `test_index_document_pauses_on_budget_exceeded_instead_of_failing` |
| A job within budget still settles and reaches `ACTIVE` exactly as before (no regression) | **Passed** — existing `test_index_document_embeds_chunks_and_upserts_points_and_marks_active` still green with the gate wired in |
| A cache-hit-only job (LAN-M3) reserves nothing at all | **Passed** — structurally guaranteed (reservation lives inside the `if miss_indices:` block) and proven by the existing cross-version cache-hit test staying green with zero budget/ledger rows created for that job |
| No regression in existing suites (LAN-M1-M4 + M0-M15 core, both apps) | **Passed** — see Test commands and results below |

### Research findings that shaped the design (verified by reading the code, not assumed)

- **Only one paid ingestion stage exists today**: `EmbeddingGateway.embed_documents` (Voyage) inside `build_indexing_points`. Parsing/chunking never call a paid API.
- **LAN-M3's embedding cache already reduces what needs reserving** — reservation had to wrap only `miss_indices` (chunks that actually need a Voyage call), not every chunk, or a cache hit would wrongly consume budget for free work.
- **Atomic claim idiom already established** by LAN-M2's lease claim (`sources_tasks.py`) — one conditional `UPDATE ... WHERE ... RETURNING`, checked by rowcount/`None`. Budget reservation reuses this exact idiom instead of introducing a `SELECT ... FOR UPDATE` pattern that doesn't exist anywhere else in this codebase. Proven race-safe by a real concurrent test (`asyncio.gather` of two reservations at the ceiling), not just argued.
- **Pause/retry precedent** from LAN-M2's disk-watermark pause (`PromotionStatus.PAUSED_CAPACITY` + `self.retry(exc=..., countdown=60)`) is the exact template for `ProcessingJobStatus.PAUSED_BUDGET` — same pause-not-fail shape, longer countdown (300s) since a budget ceiling doesn't clear on its own the way disk space might.

### Gap found and fixed during this milestone (not caught in planning)

The first migration draft used `usage_ledger_entries.source_root_id` (FK to `source_roots`). Fixed to `source_entry_id` (FK to `source_entries`, matching `DocumentVersion.source_entry_id` exactly) before it was committed — avoids an extra join at every reservation call site and matches LAN-M2's actual provenance granularity. Caught by re-checking the design against `build_indexing_points`'s actual available fields before wiring, not after.

A second gap surfaced only when running tests: `usage_ledger_entries.job_id` (FK to `processing_jobs`) and `budgets.organization_id` (FK to `organizations`) blocked `test_index_document.py`'s existing per-test cleanup (which deletes `processing_jobs` and, via the `seeded_document_version` fixture's teardown, `organizations`) with a `ForeignKeyViolationError`. Fixed by having `_cleanup()` explicitly delete `usage_ledger_entries`/`budgets` for the seeded org before the fixture's own teardown runs — matching this file's already-established explicit-cleanup style, and deliberately not relying on pytest's autouse-fixture teardown ordering (which isn't guaranteed to run in the order needed here).

### Key design decisions

- **No `STRICT_BUDGET_MODE` toggle.** "Unknown price is never treated as zero" (addendum §8) is unconditional — no config flag that could default to the wrong (unsafe) behavior.
- **All-or-nothing reservation per indexing job** — a job's estimated cost (sum of cache-miss chunks' `token_count`) is reserved in full or not at all, no partial-batch embedding.
- **Budget row created lazily** with `settings.INGESTION_BUDGET_DEFAULT_USD` the first time an org attempts a reservation (`INSERT ... ON CONFLICT DO NOTHING`, then the conditional `UPDATE`) — no admin endpoint needed to create budgets this pass.
- **`budget_type` is a column, not two schemas** — `CHAT` is a valid value from day one but only `INGESTION` is enforced this milestone.
- **Settlement reuses the pre-call token estimate**, not Voyage's real billed `total_tokens` (the API does return it, but `EmbeddingGateway.embed_documents` would need a return-shape change and its existing tests touched for a precision gain that doesn't matter for budget *control* vs. billing reconciliation) — recorded below as a deferred improvement.
- **No period/reset logic** (monthly rollover etc.) — YAGNI until a pilot actually needs one; `spent_usd`/`limit_usd` are simple running totals, resettable by direct DB edit until admin UI lands.

### Files changed

**Docs:**
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)

**apps/api:**
- `apps/api/app/indexing/models.py` — new `PricingRate`, `Budget` (`BudgetType`), `UsageLedgerEntry` (`UsageLedgerEntryStatus`)
- `apps/api/app/ingestion/models.py` — added `ProcessingJobStatus.PAUSED_BUDGET`
- `apps/api/alembic/env.py` — imports for the new models
- `apps/api/alembic/versions/f4a1c8e2b9d6_*.py` — new migration: 3 new tables, 1 new enum value, 1 seed pricing row

**workers/document_worker:**
- `app/database.py` — Core Table mirrors for `pricing_rates`/`budgets`/`usage_ledger_entries`; `processing_job_status` mirror extended with `PAUSED_BUDGET`
- `app/core/config.py` — `INGESTION_BUDGET_DEFAULT_USD`
- `app/indexing/budget.py` — new: `get_current_rate`, `reserve_ingestion_budget`, `settle_usage`, `release_reservation`, `BudgetExceededError`
- `app/indexing/pipeline.py::build_indexing_points` — reserve before the Voyage call (miss set only), release on embed failure, settle on success; gained an optional `job_id` parameter
- `app/tasks.py::_index_document_async`/`index_document` — threaded `self` through (mirrors `_promote_source_entry_async`'s existing pattern) so a caught `BudgetExceededError` sets `PAUSED_BUDGET` and calls `self.retry(...)`
- `tests/test_budget.py` — new, 9 unit tests
- `tests/test_index_document.py` — new `_FakeTask` helper (mirrors `test_sources_tasks.py`'s own), all `_index_document_async` call sites updated for the new `self` parameter, new budget-pause integration test, `_cleanup()` extended for the FK gap above

**.env.example:**
- Documented `INGESTION_BUDGET_DEFAULT_USD`

### Migrations

`f4a1c8e2b9d6` — additive: three new tables (`pricing_rates`, `budgets`, `usage_ledger_entries`), one new `processing_job_status` enum value (`PAUSED_BUDGET`, via `ALTER TYPE ... ADD VALUE`), one seed pricing row (pilot placeholder — see `.env.example`). No existing table's existing columns touched. Applied successfully (`d3e8f1a4c6b2` → `f4a1c8e2b9d6`) — hit and fixed one real issue during development (see below), not just on the first try.

**Bug caught and fixed during development, not just at the end**: the first migration attempt explicitly called `sa.Enum(...).create(op.get_bind())` for the two new enum types *and* used the same `sa.Enum(...)` objects as column types in `op.create_table(...)` — `create_table` already auto-creates an enum type the first time it's used as a column type, so the explicit `.create()` calls collided with it (`DuplicateObjectError`), rolling back the whole transaction. Fixed by removing the explicit `.create()` calls and letting `create_table` handle it, matching how the existing `a7057580f523` (LAN-M2) migration already does it.

### Test commands and results

```
cd apps/api && uv run alembic upgrade head
  -> applies cleanly (after the enum-creation fix above)

cd apps/api && uv run pytest -q
  -> 205 passed (unchanged count from LAN-M4 — schema/model additions only,
     no new apps/api endpoints or tests this milestone)

cd workers/document_worker && uv run pytest -q --ignore=tests/test_parse_document.py \
  --ignore=tests/test_pipeline.py --ignore=tests/test_region_segmenter.py --ignore=tests/test_tree_builder.py
  -> 125 passed, 1 skipped (was 115 passed, 1 skipped after LAN-M3/M4; +9
     test_budget.py + 1 new index_document budget-pause integration test)

cd workers/document_worker && uv run pytest tests/test_parse_document.py tests/test_pipeline.py \
  tests/test_region_segmenter.py tests/test_tree_builder.py -q
  -> 23 passed (unchanged — this milestone never touches the parsing pipeline)

cd workers/document_worker && uv run ruff check app/ tests/
  -> clean (after fixing two import-order issues)
```

### Assumptions not yet validated

- Everything already listed under LAN-M1-M4 still applies.
- The seeded Voyage rate (`$0.00012/1k tokens`) is a pilot placeholder, not verified against Voyage's current published pricing at any specific date — an admin UI to manage rates (with the `source` field's audit trail actually used) is deferred.
- `INGESTION_BUDGET_DEFAULT_USD` (`$50`, pilot value) has not been validated against any real ingestion volume — no real Windows LAN/SMB share has been ingested yet (same blocker as every prior milestone).
- Settlement uses the pre-call token estimate, not Voyage's actual billed `total_tokens` — a documented, deliberate simplification (see Key design decisions), not an oversight.

### Explicitly deferred (recorded, not silently dropped)

- **Admin UI** (source list, scan status, budget/coverage dashboard) — per the scoping decision above. Nothing LAN-facing exists in `apps/web` yet for any milestone.
- **Chat budget enforcement** — `BudgetType.CHAT` exists in the schema so a future milestone needs no migration to wire it up, but this pass only enforces `INGESTION`. Chat already has after-the-fact `QueryLog.estimated_cost_usd` tracking; it wasn't the addendum's stated urgent gap.
- **Period/reset logic** (monthly rollover, etc.) — YAGNI until a pilot needs one.
- **Real Voyage `total_tokens` reconciliation** at settlement time, instead of the pre-call estimate — would require changing `EmbeddingGateway.embed_documents`'s return shape and touching its existing tests for a precision gain that doesn't matter for budget control.
- **Per-org budget-limit admin endpoint** — budgets are currently only created lazily at the configured default; adjusting a specific org's limit requires a direct DB edit until admin UI lands.

### Blockers

- Same as LAN-M1-M4: no real Windows LAN/SMB share reachable from this dev environment.

### Next step

LAN-M5 is complete per its acceptance criteria (backend scope). Per Operating Rule #3, **do not** proceed to LAN-M6 (pilot and operations guide) automatically — re-read this file plus the implementation plan's LAN-M6 section first.

## LAN-M4: End-to-end access and retrieval — **complete**

Scoped to **audit + regression tests, viewer endpoint deferred** (a deliberate decision, confirmed before starting): the addendum's stated requirements (tenant scoping across retrieval-adjacent paths, curated-access-by-default, immediate revocation) turned out to already be fully satisfied by the existing architecture, verified by reading the actual code before writing anything. The one genuinely new thing the addendum names — an authenticated document viewer/download endpoint — doesn't exist for **any** document type today, LAN-sourced or uploaded, so building one isn't a LAN-specific gap; it's deferred to a follow-up milestone, same framing as legacy `.doc` in LAN-M3. Full Windows-ACL mode is likewise deferred — the addendum itself calls it "LAN-M4's own separate work."

### Acceptance criteria status

| Criterion | Status |
|---|---|
| A LAN-sourced document's chunks are retrievable with identical cross-org isolation as an uploaded document | **Passed** — `test_org_a_cannot_exact_match_org_bs_lan_sourced_article` |
| Archiving a LAN-sourced document revokes it immediately, with no dependency on any rescan/ingestion cycle | **Passed** — `test_archiving_a_lan_sourced_document_revokes_it_immediately` |
| No regression in existing suites (LAN-M1/M2/M3 + M0-M15 core) | **Passed** — see Test commands and results below |

### Why this milestone needed almost no new production code

Every principle the addendum's §7 names for LAN-M4 turns out to already hold, because LAN-M2 made a specific design choice that pays off here: a LAN-promoted document is a plain `Document`/`DocumentVersion` row (only `DocumentVersion.source_entry_id` marks its origin) that flows through the exact same pipeline as an ordinary upload. Verified directly, not assumed:

- **Tenant scoping across retrieval/reranker/evidence/citations/cache**: `retrieval/service.py::_fetch_verified_chunks` already filters strictly by `organization_id` + `ACTIVE` status (+ optional `knowledge_space_id`) for both exact-match and hybrid retrieval, with zero awareness of document source. `RerankingService.select_evidence` and `AdaptiveCitationService.build_citations` both take an already-tenant-scoped chunk/evidence list as **input** — neither re-queries the database independently — so there is no separate code path for "reranker tenant scoping" or "citation tenant scoping" to test; they inherit retrieval's guarantee by construction. `AnswerCacheService` keys are already organization-prefixed (ADR-018).
- **"Curated access by default"** is already exactly the existing `OrgRole`/knowledge-space-membership authorization — nothing LAN-specific to add.
- **"Revocation immediate, independent of ingestion cycle"**: `POST /documents/{id}/archive` already exists (flips `ACTIVE`→`ARCHIVED`, invalidates the answer cache synchronously, and retrieval already re-verifies status live against Postgres) and works identically on LAN-promoted documents with zero changes — confirmed with a real test, not just code reading.

### Key design decision

Rather than writing new production code to satisfy requirements that already hold, this milestone added the regression tests that **prove** they hold specifically for LAN-sourced documents — closing the risk that this was an untested assumption. Two tests were sufficient (not one per named path) because reranker/evidence/citations/cache have no independent tenant-scoping logic of their own to test separately; they all consume `RetrievalService`'s already-verified output.

### Files changed

**Docs:**
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)

**apps/api:**
- `apps/api/tests/integration/_retrieval_fixtures.py` — new `seed_lan_source_entry` helper; `seed_active_document` gained an optional `source_entry_id` parameter (default `None`, preserving existing callers' behavior unchanged)
- `apps/api/tests/integration/test_retrieval_tenant_isolation.py` — two new tests (see acceptance criteria table)

### Test commands and results

```
cd apps/api && uv run pytest -q
  -> 205 passed (was 203 after LAN-M3; +2 new LAN-M4 regression tests)

cd apps/api && uv run pytest tests/integration/test_retrieval_tenant_isolation.py -q
  -> 6 passed (was 4 after M7/M13; +2 LAN-M4 tests)
```

### Assumptions not yet validated

- Everything already listed under LAN-M1/LAN-M2/LAN-M3 still applies.
- No new coverage was added to `tests/e2e`'s golden-path/RAG-eval harness for a LAN-sourced document specifically — the two integration tests added here exercise the same `RetrievalService`/`archive_document` code the e2e harness already covers for uploads, so this was judged sufficient rather than redundant. Revisit if a future milestone's e2e harness changes shape in a way that could diverge by source type.

### Explicitly deferred (recorded, not silently dropped)

- **Authenticated document viewer/download endpoint** — per the scoping decision above. Doesn't exist for any document type yet; the addendum's constraint ("never a raw UNC path in the browser") is a principle to hold *when* it's eventually built, not a mandate to build it now.
- **Full Windows-ACL mode** (identity/group mapping, freshness sync, fail-closed policy) — explicitly optional per the addendum's own framing ("LAN-M4's own separate work"). The curated-access default (`OrgRole`) is what's actually implemented and tested.

### Blockers

- Same as LAN-M1/M2/M3: no real Windows LAN/SMB share reachable from this dev environment.

### Next step

LAN-M4 is complete per its acceptance criteria. Per Operating Rule #3, **do not** proceed to LAN-M5 (cost control and admin UI) automatically — re-read this file plus the implementation plan's LAN-M5 section first.

## LAN-M3: DOCX parsing and embedding cache — **complete**

Scoped to **DOCX only** (a deliberate decision, confirmed before starting): legacy binary `.doc` needs a separate sandboxed converter (macros/external resources disabled, subprocess timeout/memory limits) and is deferred to a follow-up milestone. No code change was needed for `.doc` to keep failing cleanly — `ALLOWED_EXTENSIONS` already excluded it at both the ordinary upload path and LAN promotion since LAN-M2.

### Acceptance criteria status

| Criterion | Status |
|---|---|
| A real `.docx` parses to `PARSED` status instead of incorrectly failing | **Passed** — `test_run_pipeline_on_docx_parses_cleanly_with_no_page_provenance` |
| DOCX region segmentation covers every item with no gaps, in document order | **Passed** — `test_segment_regions_on_docx_falls_back_to_position_based_segmentation`, `test_segment_regions_on_docx_are_contiguous_and_ordered` |
| DOCX nodes resolve to the correct region without a page number | **Passed** — `test_build_tree_on_docx_has_no_page_numbers_but_correct_regions` |
| DOCX LAMPIRAN/appendix-style sections are still detected | **Passed** — `test_segment_regions_on_docx_detects_appendix_section` |
| Citations/evidence never require a page number; structural_path_text stands alone for DOCX | **Passed** — schema/model changes verified by the full apps/api suite + frontend typecheck |
| Embedding cache: hit avoids a Voyage call entirely, across unrelated document versions | **Passed** — `test_index_document_reuses_cached_embedding_for_identical_chunk_text_across_versions` |
| Embedding cache: key changes on model revision/dimension/normalization (no false-positive hit) | **Passed** — `test_cache_key_changes_with_*` (test_embedding_cache.py) |
| Embedding cache: concurrent insert of the same key doesn't error | **Passed** — `test_storing_the_same_key_twice_does_not_error_or_duplicate` |
| No regression in existing suites (LAN-M1/M2 + M0-M15 core, both apps + frontend) | **Passed** — see Test commands and results below |

### Root cause found before writing any code

`.docx` was already accepted end-to-end at both the ordinary upload path (`apps/api/app/ingestion/validation.py`) and LAN promotion (`workers/document_worker/app/sources/promotion.py`) since LAN-M2 — but Docling was only ever configured for PDF, and the parsing pipeline (`page_classifier.py`/`region_segmenter.py`/`tree_builder.py`) was built entirely around Docling's per-page stats. Verified directly: `DoclingDocument.pages` is `{}` for a converted DOCX and every item's `item.prov` is `[]` (no page numbers at all). This meant **any real `.docx` upload before this milestone silently produced `PROCESSING_FAILED`** — a live correctness bug, not just a missing feature.

`tree_builder.py` already tolerated `page_no=None` per node (`has_direct_page` field) — it was already written with ADR-014's generic-structure-first principle in mind. The one place that was actually wrong was `_region_for_page`'s `None` fallback, which unconditionally returned the last region — fine as a bug nobody had hit yet, since nothing before this milestone ever produced a region list for a page-less document at all.

### Gap found and fixed during this milestone (not caught in planning)

`apps/api`'s ORM models (`DocumentRegion`, `DocumentNode`, `DocumentChunk`, `MessageSource`) declared `page_start`/`page_end` as `nullable=False`, even though the worker's plain Core Table mirror in `database.py` had no such constraint (defaults to nullable). The plan assumed no migration was needed based on the worker's mirror alone — wrong; the authoritative apps/api schema needed a real migration. Fixed via `c1f4a2e9b7d3` (additive, widens NOT NULL to nullable, no existing row affected — verified no row could be non-null-violating since old rows keep their existing non-null values).

Also found and fixed in passing: `apps/api/alembic/env.py` was missing `PromotionRecord` from its autogenerate import list (a LAN-M2 gap — every other `sources.models` class was imported except this one). Fixed alongside adding `EmbeddingCacheEntry`'s own import, since both belong in the same import block.

### Key design decisions

- **Position-based segmentation, not a second segmentation engine.** `region_segmenter.py` gained a document-order (`_segment_by_position`) path that reuses the exact same TOC/LAMPIRAN/cover-page heuristics as the page-based path, just keyed on item sequence index instead of page number. `RegionRecord` gained `sequence_start`/`sequence_end` (nullable, only set for non-paginated regions) alongside making `page_start`/`page_end` nullable.
- **`tree_builder.py`'s node-to-region resolution** (`_region_for_page` → `_region_for_node`) now takes both a page number and a position, using whichever axis is available — mirrors `_backfill_group_page_ranges` with a new `_resolve_group_positions` for the position axis on `GroupItem` nodes.
- **`pipeline.py` needed zero changes.** Once `region_segmenter.py` correctly handles the empty-`page_stats` case, the existing "no regions ⇒ `PROCESSING_FAILED`" check and the OCR escalation cascade (`categories = {classify_page(stat) for stat in page_stats}` — empty for DOCX, so escalation never triggers) both already do the right thing for DOCX with no modification. Confirmed by direct testing, not assumed.
- **Embedding cache is global, not tenant-scoped** — a dense embedding only depends on `contextual_text` (which already carries the structural prefix baked in, per `chunking/contextual_text.py`) plus embedding config, never on which tenant/document it came from. New `embedding_cache_entries` table, key = `sha256(contextual_text|model|revision|dimension|normalized)`. Two new config knobs (`EMBEDDING_MODEL_REVISION`, `EMBEDDING_NORMALIZED`) exist purely to be bumped by hand if Voyage ever silently updates a model's weights under the same name.
- **`build_indexing_points` needed no signature change.** Cache lookup/write uses its own short `async_session_factory()` sessions internally, decoupled from the caller's job-processing transaction — a successfully computed embedding is worth keeping even if the indexing job later fails at the Qdrant-upsert step.

### Files changed

**Docs:**
- `docs/LAN_ARCHIVE_PROGRESS.md` (this file)

**apps/api:**
- `apps/api/app/reranking/schemas.py`, `apps/api/app/citations/schemas.py`, `apps/api/app/retrieval/schemas.py`, `apps/api/app/parsing/schemas.py` — `page_start`/`page_end` → `int | None`
- `apps/api/app/chunking/models.py`, `apps/api/app/parsing/models.py`, `apps/api/app/chat/models.py` — matching ORM columns → nullable
- `apps/api/app/indexing/models.py` — new: `EmbeddingCacheEntry`
- `apps/api/alembic/env.py` — added `EmbeddingCacheEntry` import, fixed the missing `PromotionRecord` import
- `apps/api/alembic/versions/c1f4a2e9b7d3_*.py` — new migration: `page_start`/`page_end` nullable on `document_regions`/`document_nodes`/`document_chunks`/`message_sources`
- `apps/api/alembic/versions/d3e8f1a4c6b2_*.py` — new migration: `embedding_cache_entries` table

**workers/document_worker:**
- `workers/document_worker/app/parsing/docling_adapter.py` — registered `WordFormatOption` for `InputFormat.DOCX`
- `workers/document_worker/app/parsing/region_segmenter.py` — document-order segmentation path, nullable `page_start`/`page_end`, new `sequence_start`/`sequence_end`
- `workers/document_worker/app/parsing/tree_builder.py` — `_region_for_page` → `_region_for_node` (page or position), new `_resolve_group_positions`
- `workers/document_worker/app/indexing/embedding_cache.py` — new: cache key, get, store
- `workers/document_worker/app/indexing/pipeline.py` — wired the cache into `build_indexing_points`
- `workers/document_worker/app/database.py` — added `embedding_cache_entries` mirror
- `workers/document_worker/app/core/config.py` — added `EMBEDDING_MODEL_REVISION`, `EMBEDDING_NORMALIZED`
- `workers/document_worker/pyproject.toml` — added `python-docx` (dev dependency, DOCX test fixtures)
- `workers/document_worker/tests/fixtures.py` — new `digital_text_docx()` fixture
- `workers/document_worker/tests/test_pipeline.py`, `test_region_segmenter.py`, `test_tree_builder.py` — new DOCX coverage
- `workers/document_worker/tests/test_embedding_cache.py` — new, 7 unit tests
- `workers/document_worker/tests/test_index_document.py` — new cross-version cache-hit integration test
- `workers/document_worker/tests/conftest.py` — new autouse fixture clearing `embedding_cache_entries` between tests (the cache is global, so it doesn't get cleaned up by the existing per-org teardown)

**apps/web:**
- `apps/web/src/lib/chat-schemas.ts`, `apps/web/src/lib/documents-api.ts` — matching TS types → `number | null`
- `apps/web/src/components/chat/SourceDrawer.tsx`, `apps/web/src/components/documents/test-knowledge-panel.tsx` — render `structural_path_text` alone when `page_start` is `null`

**.env.example:**
- Documented `EMBEDDING_MODEL_REVISION`, `EMBEDDING_NORMALIZED`

### Migrations

- `c1f4a2e9b7d3` — additive: widens `page_start`/`page_end` from `NOT NULL` to nullable on `document_regions`, `document_nodes`, `document_chunks`, `message_sources`. Safe — no existing row's value changes, only new DOCX-sourced rows will ever actually store `NULL`.
- `d3e8f1a4c6b2` — additive: new `embedding_cache_entries` table only, no existing table touched.
- Both applied successfully (`a7057580f523` → `c1f4a2e9b7d3` → `d3e8f1a4c6b2`).

### Test commands and results

```
cd apps/api && uv run pytest -q
  -> 203 passed (unchanged count from LAN-M2 — this milestone's apps/api
     changes are schema/model nullability, not new endpoints/tests)

cd workers/document_worker && uv run pytest -q --ignore=tests/test_parse_document.py \
  --ignore=tests/test_pipeline.py --ignore=tests/test_region_segmenter.py --ignore=tests/test_tree_builder.py
  -> 115 passed, 1 skipped (was 107 passed, 1 skipped after LAN-M2; +7
     test_embedding_cache.py + 1 cross-version cache-hit integration test)

cd workers/document_worker && uv run pytest tests/test_parse_document.py tests/test_pipeline.py \
  tests/test_region_segmenter.py tests/test_tree_builder.py -q
  -> 23 passed (was 18 after LAN-M2; +5 DOCX tests across pipeline/region_segmenter/
     tree_builder — same known-harmless "Windows fatal exception: access violation"
     background-thread noise, per windows-toolchain-quirks memory, did not fail the run)

cd apps/web && pnpm tsc --noEmit --pretty false
  -> clean, no errors

cd apps/web && pnpm eslint src/lib/chat-schemas.ts src/lib/documents-api.ts \
  src/components/chat/SourceDrawer.tsx src/components/documents/test-knowledge-panel.tsx
  -> clean, no errors

cd apps/web && pnpm vitest run tests/render-citations.test.tsx tests/structure-tree.test.tsx \
  tests/test-knowledge-panel.test.tsx
  -> 12 passed (3 test files)
```

### Assumptions not yet validated

- Everything already listed under LAN-M1/LAN-M2 (production OS/deployment shape, real Windows LAN/SMB topology) still applies.
- `packages/schemas/src/api-types.ts` (generated from apps/api's live OpenAPI schema) was **not regenerated** this milestone — it requires a running FastAPI dev server. Confirmed it's safe to defer: the only field `apps/web` currently derives from that generated file is `DocumentLifecycleStatus`, unaffected by this milestone's schema changes. Regenerate before the next milestone that actually consumes a changed field from it.
- Table cells inside a DOCX are parsed and their text is included in region-classification stats, but there is no DOCX-specific test asserting a table survives into `document_nodes`/`document_chunks` correctly (structurally, table handling in `tree_builder.py`'s `_add_table_children` is format-agnostic and already exercised by the PDF suite) — worth a dedicated DOCX-table test if a real client document surfaces an issue.

### Explicitly deferred (recorded, not silently dropped)

- **Legacy `.doc` sandboxed converter** — per the scoping decision above.
- **"Structure reconciliation across page-batch processing"** (batched Docling conversion for very large files) — no code in the pipeline does batching today (whole file converted in one `convert()` call regardless of format); nothing in this codebase currently needs it. Deferring until real file-size data from LAN-M6 sampling shows it's actually needed, same as how LAN-M2 deferred its stability-check optimization.
- **LAN-M4's "active generation"/staging-index concept** — already exists and needed no new work: `tasks.py::_index_document_async` already upserts Qdrant with the post-activation payload *before* the Postgres commit that flips `document_versions.status` to `ACTIVE`, and retrieval re-verifies status live against Postgres. That already **is** the "Qdrant-payload-prefilter-plus-Postgres-reverification" pattern the plan called for reusing.

### Blockers

- Same as LAN-M1/LAN-M2: no real Windows LAN/SMB share reachable from this dev environment.

### Next step

LAN-M3 is complete per its acceptance criteria. Per Operating Rule #3, **do not** proceed to LAN-M4 (end-to-end access and retrieval) automatically — re-read this file plus the implementation plan's LAN-M4 section first.

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

- **LAN-M6** — pilot/operations guide, partial: backup/restore, rollback plan, and staged rollout guidance written; sampling/benchmarking/retrieval-eval/cost-projection remain blocked on real client access. See above.
- **LAN-M5** — ingestion budget control: usage ledger, versioned pricing config, atomic reserve/settle/release, budget-paused-not-failed jobs. Admin UI and chat-budget enforcement explicitly deferred. See acceptance criteria table above.
- **LAN-M4** — end-to-end access/retrieval audit: verified (with regression tests, not just code reading) that tenant scoping and immediate revocation already work identically for LAN-sourced documents; viewer endpoint and Windows-ACL mode explicitly deferred. See acceptance criteria table above.
- **LAN-M3** — DOCX parsing (page-optional pipeline generalization) and embedding cache. See acceptance criteria table above.
- **LAN-M2** — selective snapshot/promotion into the existing document pipeline, streaming transfer, dedup, disk watermark, crash-safe lease-based idempotency. See acceptance criteria table above.
- **LAN-M1** — source registry, adapter contract, catalog-only discovery. 9/9 acceptance criteria passed; `WindowsUNCAdapter` implemented but real-UNC validation still pending client environment access.
