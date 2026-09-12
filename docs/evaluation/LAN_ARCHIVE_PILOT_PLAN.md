# LAN Archive Pilot Plan

Status per `docs/LAN_ARCHIVE_PROGRESS.md`: LAN-M1 through LAN-M5 are
complete. This document is LAN-M6's own deliverable, filled in
incrementally rather than all at once — per a scoping decision made
explicitly with the user, the parts that need no real client data
(backup/restore, rollback, staged rollout guidance) are written now,
against the actual mechanisms this track built. The parts that fundamentally
require a real client environment (representative sampling, real LAN
transfer-rate benchmarks, retrieval evaluation on real Indonesian
regulatory documents, cost projection from real extraction results) remain
explicitly blocked below, not fabricated — same reasoning as before: writing
benchmark targets or cost projections without real data would be fabricated
numbers presented as measurements, prohibited by this track's own operating
rules (`docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md` §8, §10).

## Backup and restore procedures

This system's durability story follows ADR-001 (PostgreSQL as source of
truth): everything that isn't Postgres is either derived from it or holds
data Postgres doesn't have a copy of. Back up accordingly, not uniformly.

| Store | Role | Backup approach | Restore approach |
|---|---|---|---|
| **PostgreSQL** | Source of truth for all document/chunk/region/node/job/budget/ledger state | `pg_dump` (logical) or `pg_basebackup` + WAL archiving (physical, enables point-in-time recovery) on the standard schedule for the deployment's RPO/RTO targets | Standard `pg_restore`/WAL replay. Everything else in this table is rebuildable or re-derivable from a restored Postgres, so this is the backup that actually matters most. |
| **MinIO/S3** (`apps/api/app/core/storage.py`) | Holds the *original* uploaded/promoted file content (`document_versions.storage_path`) — Postgres has no copy of file bytes | Object storage's own replication/versioning (MinIO server-side replication, or S3 versioning + cross-region replication) — independent of the Postgres backup schedule | Restore from the object store's own mechanism. **Not derivable from Postgres** — if both a Postgres backup and the object storage are lost for the same document, that document's original file is gone and would need to be re-obtained from the client's LAN share (if `source_entry_id` is set) or re-uploaded. |
| **Qdrant** | Derived vector/sparse index — every point is rebuildable from Postgres's `document_chunks` (`workers/document_worker/app/indexing/pipeline.py::build_indexing_points`) | Qdrant's own snapshot API (`POST /collections/{name}/snapshots`) for fast restore without re-embedding cost; not strictly required since the index is fully re-derivable | **Preferred**: restore from a Qdrant snapshot (no Voyage cost). **Fallback**: re-run `index_document` for every `ACTIVE` `DocumentVersion` — this re-embeds everything and is gated by LAN-M5's budget mechanism, so a full-collection rebuild can't silently blow past the ingestion budget; size the budget accordingly *before* triggering one. |
| **`embedding_cache_entries`** (LAN-M3) | Pure performance optimization, content-addressable | None needed | Losing it entirely is safe — the next embedding call for that text/config just becomes a cache miss and re-embeds (budget-gated as normal). Never a backup priority. |
| **Redis** (answer cache, rate limiting) | Ephemeral, TTL-bound | None needed | Empty cache on restore is correct behavior, not a degraded state. |

**Closed**: if a worker crashes between `reserve_ingestion_budget` and
`settle_usage`/`release_reservation`
(`workers/document_worker/app/indexing/budget.py`), a `usage_ledger_entries`
row could previously be left `RESERVED` indefinitely, permanently reducing
that organization's usable budget headroom by the reserved amount. Celery's
`autoretry_for`/`self.retry()` on `index_document` only ever covered the
*job* retrying, never a genuinely lost worker process before settlement.
`reconcile_stale_reservations()` now releases any `RESERVED` entry older
than `BUDGET_RESERVATION_STALE_SECONDS` (1800s default), wired as the
`document_worker.reconcile_stale_budget_reservations` Celery task with a
15-minute `beat_schedule` entry. **Operational caveat**: this only actually
fires if a `celery beat` process is running — this repo doesn't deploy one
yet (see `workers/document_worker/README.md`'s manual-invocation command).
Confirm `celery beat` is part of the deployment, or schedule the manual
invocation externally, before relying on this at real production budget
volumes.

## Rollback plan

Distinguish three different things this track already calls "rollback" at
different granularities — don't conflate them operationally:

1. **A single bad document version** — already solved, no new mechanism
   needed. `POST /documents/{id}/archive` (LAN-M4) immediately flips
   `ACTIVE` → `ARCHIVED`, invalidates the organization's answer cache
   synchronously, and retrieval already re-verifies status live against
   Postgres — the document stops being usable as evidence within the same
   request cycle, with no ingestion-cycle dependency and no data loss (the
   row is archived, never deleted).
2. **A schema migration** — standard `alembic downgrade <revision>`. One
   documented limitation: Postgres has no `ALTER TYPE ... DROP VALUE`, so
   `f4a1c8e2b9d6`'s downgrade (LAN-M5) cannot remove
   `ProcessingJobStatus.PAUSED_BUDGET` from the enum — the same accepted
   limitation as any additive enum-value migration in this codebase.
3. **A crashed ingestion job mid-promotion** — already solved, automatic,
   not a manual step. LAN-M2's lease-based idempotency
   (`workers/document_worker/app/sources_tasks.py`) means a crashed
   worker's stale lease is reclaimed by a later attempt; no promotion is
   silently lost or duplicated.

**Closed**: `POST /sources/{id}/disable` (OWNER/ADMIN) now stops a
misconfigured `SourceRoot` from accepting new scans/promotions —
`trigger_scan`/`promote_entries` return 409 while disabled — without
deleting the source or its already-promoted documents. `POST
/sources/{id}/enable` reverses it. If some already-promoted documents
shouldn't stay active, archive them separately (#1 above). Verify at Phase
0 below that the source is enabled (it is, by default) rather than
assuming disable is unnecessary to know about.

## Staged production rollout guidance

Each phase's exit criteria gate the next phase — do not skip ahead because
an earlier phase looked fine on a small sample.

**Phase 0 — Dry-run discovery only (LAN-M1).** Register the real
`SourceRoot` (`WINDOWS_UNC`, read-only service account, explicit UNC path,
explicit subtree allowlist). Run catalog-only scans. Review
`GET /sources/{id}/entries` manually — this is metadata only, zero content
read, zero cost. Exit criteria: scan completes with an acceptable
`partial`/error rate (per `docs/operations/LAN_CONNECTOR_RUNBOOK.md`'s
troubleshooting table), and an admin has manually verified the catalogued
file types/counts look like what the client actually described. Also verify
here — per the rollback-plan gap above — that everyone involved understands
there's no "undo" button on a source registration beyond not promoting from
it.

**Phase 1 — Small controlled promotion (LAN-M2/M3).** Manually select a
handful (5-10) of representative documents — mixed PDF/DOCX, at least one
scanned PDF to exercise OCR escalation, at least one large/complex
document. Promote via `POST /sources/{id}/entries/promote`. Verify each
reaches `ACTIVE` and spot-check parsing quality: correct region
segmentation, correct `structural_path_text`, no fabricated `Pasal`
numbers on a non-`Pasal` document, DOCX evidence correctly falling back to
`structural_path_text` with no page number. Exit criteria: parsing quality
judged acceptable by someone who can read the source documents; any
failures triaged (parser bug vs. genuinely unusual document) before
proceeding.

**Phase 2 — Budget-gated ingestion at pilot scale (LAN-M5).** Before this
phase: set a **real** per-organization ingestion budget limit — the
current `INGESTION_BUDGET_DEFAULT_USD` (pilot placeholder, `$50`) and the
seeded Voyage rate (pilot placeholder, see `.env.example` and
`docs/LAN_ARCHIVE_PROGRESS.md`'s LAN-M5 section) are almost certainly wrong
for a real client and must be reviewed first. Promote the eventual
sampling batch (300-500 documents, adjusted for real access/budget — see
"Blocked" section below for the actual sampling methodology). Monitor for
`ProcessingJobStatus.PAUSED_BUDGET` — a paused job here is the budget gate
working as intended, not a bug; investigate whether the limit needs
raising or the pause is catching a genuine cost anomaly before just
increasing the number. Exit criteria: batch completes (or pauses are
explained and resolved deliberately) within the reviewed budget.

**Phase 3 — Retrieval and access validation (LAN-M4).** Confirm the
curated-access default (`OrgRole`/knowledge-space membership) actually
matches the client's real authorization model. Explicitly decide — don't
default into — whether full Windows-ACL mode is actually needed; it is
deferred, separate work, not something to build speculatively. Exit
criteria: a knowledgeable client-side reviewer confirms retrieval/citation
behavior on the Phase 1/2 documents meets expectations.

**Phase 4 — Full-scale rollout with monitoring.** Before go-live: verify a
**restore has actually been tested**, not just documented — a written
backup procedure that has never been exercised is not a verified backup
procedure. Roll out remaining volume in budget-gated batches (never as one
unbounded ingestion run), with the same monitoring as Phase 2.

**Rollback triggers** (stop and revisit rather than push forward): parsing
quality below acceptable threshold in Phase 1 → do not proceed to Phase 2.
Budget burn rate exceeds projection in Phase 2 → the gate already pauses
automatically; the human action is to revisit the budget/pricing config
deliberately, not just raise the limit reflexively. Retrieval/citation
quality issues surfaced in Phase 3 → archive the affected documents
(rollback plan #1) and do not proceed to Phase 4 until resolved.

## Blocked pending real client access/credentials

Everything below still requires data this dev environment does not have —
recorded as blocked, not attempted with synthetic substitutes presented as
real numbers.

- **Sampling methodology**: a representative sample across PDF-text,
  PDF-scanned, DOCX, and (if in scope) legacy DOC documents, stratified by
  file size. 300-500 documents is a starting point from the source
  requirements doc, explicitly adjustable for real access/budget — not a
  statistical representativeness guarantee. The actual sample plan needs
  real document-type proportions from the client's share, currently
  unknown.
- **Cost projection**: extraction results from the Phase 2 sample, used to
  project a cost range for fuller ingestion — never a direct 4TB-to-token
  conversion (explicitly forbidden, addendum §8).
- **Benchmarks**: OCR throughput, embedding throughput, real LAN transfer
  rate, retry rate, and p50/p95 chat latency with ingestion idle vs. active
  — all need to run against real files over a real LAN connection to mean
  anything; a synthetic/local benchmark would measure this dev machine, not
  the client's actual environment.
- **Retrieval evaluation**: real Indonesian regulatory queries — article/
  number lookups, cross-section questions, and questions with genuinely no
  evidence (verifying the system says so rather than guessing) — needs the
  client's real regulatory corpus, not synthetic test fixtures.

This section gets filled in incrementally as real inputs become available,
not written in one pass.
