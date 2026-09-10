# LAN Archive Implementation Plan

Milestone track for ingesting a Windows LAN file-share archive (up to ~4TB)
into the existing knowledge base. Extends `docs/MASTER_DEVELOPMENT_SPEC.md`'s
milestones (M0-M15) without renumbering them — this track uses the `LAN-M`
prefix and can proceed independently once its own dependencies are met.
Architecture context: `docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md`.
Connector deployment decision: `docs/adr/ADR-020-lan-archive-source-connector.md`.

Per this repo's Operating Rules (`CLAUDE.md`): one milestone at a time, no
architecture change without an ADR, run tests after every change, never
shortcut tenant isolation. Every new endpoint in this track is tenant-scoped
and auth-gated from the milestone it's introduced in — security is never
deferred to a later milestone.

## LAN-M1: Audit, source foundation, catalog without AI cost — **this milestone**

**Target:**
- Gap matrix, ADR-020, this plan, progress doc, runbook, pilot-plan stub.
- Tenant-scoped `SourceRoot`/`SourceEntry`/`ScanRun` data model + additive migration.
- Adapter `Protocol` + `LocalFakeAdapter` (tests/dry-run) + `WindowsUNCAdapter` (production shape, unvalidated against a real share).
- Paginated, checkpointed discovery scan — catalog-only, zero provider calls, zero file copies.
- Admin API: register a source, list sources, trigger a dry-run scan, view scan runs and entries.
- Config additions (`CONNECTOR_ENABLED`, allowed hosts/shares, scan page size, revised `MAX_FILE_SIZE_MB`).

**Acceptance criteria:**
1. Migration applies cleanly (`alembic upgrade head`) on the existing dev DB with no changes to existing tables.
2. A `LOCAL_FAKE` source can be registered, scanned, and produces `SourceEntry` rows with correct `discovery_status`, entirely through the admin API.
3. A scan against an unreachable/offline source does not mark existing entries as missing.
4. A scan where one subtree is inaccessible still completes for the rest, with that subtree's failure recorded separately.
5. A re-scan with no source changes produces no new `SourceEntry` rows and no duplicate `ScanRun` side effects.
6. Discovery never calls Docling, an embedding gateway, an LLM gateway, or `put_object` — verified by test (mocked/spied, asserting zero calls).
7. All new endpoints require organization membership at the correct role and are tenant-scoped (cross-org access returns 404, matching existing convention).
8. Full existing test suites (`apps/api`, `workers/document_worker`) still pass — no regression.
9. `WindowsUNCAdapter` exists and is exercised by unit tests using a real local filesystem (not a real UNC share) — real-share validation is explicitly recorded as pending in the runbook, never claimed as passing.

**Out of scope for LAN-M1:** anything in LAN-M2 through LAN-M6 below.

## LAN-M2: Selective snapshot and incremental sync

Promotion policy (admin selects catalog entries to become candidates), streaming staging with bounded buffer/checksum, file-stability detection (two separate stable-metadata checks, ignore lock/temp files like `~$*.docx`), version/provenance recording, safe content dedup (identity preserved separately from content reference), queue idempotency keyed on document version + pipeline config, crash recovery via lease/heartbeat/fencing (closes the gap noted in the addendum §6), temp quota + disk-watermark guard.

**Depends on:** LAN-M1's `SourceEntry`/`SourceRoot` and adapter's `open_stream`.

## LAN-M3: PDF/Word parsing and versioned index

DOCX/DOC parsing added alongside the existing Docling PDF pipeline (net new — Docling here is PDF-only today). Structure reconciliation across page-batch processing. Contextual-prefix embedding cache keyed on final embedded text + prefix + model/revision/dimension/normalization (closes the "no embedding cache" gap). Staging index generation concept, built as an extension of the existing Qdrant-payload-prefilter-plus-Postgres-reverification pattern already proven in `retrieval/service.py`, not a new mechanism.

**Depends on:** LAN-M2's snapshot/version pipeline.

## LAN-M4: End-to-end access and retrieval

Tenant/scope enforcement extended across every retrieval-adjacent path (lexical search, parent expansion, reranker, evidence fetch, cache, viewer, download) for LAN-sourced documents. Explicit curated-access mode by default; full Windows-ACL mode only if the client's environment requires it and source identity is available. Revocation that takes effect immediately, independent of the ingestion cycle.

**Depends on:** LAN-M3's active generation concept.

## LAN-M5: Cost control and admin UI

Usage ledger (tenant/source/job/stage/provider), versioned+dated pricing config, atomic budget reservation/settlement, ingestion budget separate from chat budget, pause/resume preserving checkpoints, cost/coverage admin UI. A basic budget gate must exist before any milestone runs real paid ingestion at volume — LAN-M2/M3 use mock/dry-run providers in development until this gate lands, per the source prompt's explicit requirement.

**Depends on:** usage data becoming available once LAN-M2/M3 make real provider calls.

## LAN-M6: Pilot and operations guide

Representative sampling (300-500 documents as a starting point, adjusted for real access/budget — not a statistical guarantee), benchmarking (OCR/embedding throughput, LAN transfer rate, p50/p95 chat latency with ingestion idle vs. active), retrieval evaluation on real Indonesian regulatory queries, backup/restore and rollback procedures, staged production rollout guidance.

**Depends on:** a working LAN-M1..LAN-M5 pipeline and client-provided access/credentials.

## Testing strategy (applies across all milestones)

Synthetic fixtures only — no client data ever. Tests must exercise
behavior/risk, not just re-assert what the mock does. See
`docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md` §10 and the source
requirements doc's full scenario table (`PROMPT_CLAUDE_CODE_UPDATE_CHATBOT_4TB.md`
§13) for the complete list this track is accountable to over its lifetime —
LAN-M1's own subset is in this file's LAN-M1 acceptance criteria above.
