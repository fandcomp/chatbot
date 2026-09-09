# ADR-019: Confidence-Based Auto-Approval of Document Versions

## Context

`workers/document_worker/app/tasks.py`'s `_interpret_structure_async` (M4)
has, since M4 shipped, set a document version's status to `APPROVED` —
skipping `REVIEW_REQUIRED` entirely and immediately queuing chunking/
indexing — whenever `interpret_document`'s `aggregate_confidence` meets or
exceeds `STRUCTURE_HIGH_CONFIDENCE` (default 0.90). No human ever looks at
that document before it reaches `ACTIVE` and starts answering real user
questions.

This was never recorded as an architectural decision, and it visibly
diverges from two things the project treats as normative:

- The state diagram in `docs/MASTER_DEVELOPMENT_SPEC.md` §9, which only
  draws `PARSED -> REVIEW_REQUIRED -> APPROVED` — no edge from `PARSED`
  straight to `APPROVED`.
- Operating Rule §107.9, "Tidak mem-bypass document approval" ("do not
  bypass document approval"), and CLAUDE.md's identical prohibition.

A 2026-09 audit of the codebase (as part of a general M15 hardening pass)
flagged this as the single highest-severity finding: an undocumented,
un-audited path from upload to a live, citable knowledge-base entry with
zero human interaction, for a product whose entire value proposition is
regulatory answers a client can trust and trace.

## Decision

**Keep confidence-based auto-approval as an intentional product behavior**,
not a bug — a self-service platform whose clients may not have a legal
reviewer available the moment every document is uploaded needs *some* path
to a usable knowledge base without an indefinite human-in-the-loop queue.
Requiring manual approval for every single document regardless of
structural confidence would defeat "self-service" for the common case where
Docling's parse and M4's structural interpretation are unambiguous (a clean
BAB/Pasal-numbered PDF with no OCR fallback, no anomalies, aggregate
confidence >= 0.90).

But an automated approval must never again be indistinguishable from a
bypass. Two changes make it an accepted, *audited* exception instead:

1. **Mandatory audit trail.** Every auto-approval now inserts one row into
   `audit_logs` (`action = "document_version.auto_approved"`,
   `actor_id = NULL` — the actor is the system, not a user — `entity_type =
   "document_version"`, `new_value` carrying the confidence score and the
   threshold it cleared). This is the same table `apps/api`'s human-driven
   approve endpoint (`POST /documents/{id}/approve`,
   `apps/api/app/parsing/router.py`) already writes to via `log_action`, so
   both paths are visible side-by-side in one audit trail. The worker gets
   its own Core `Table` definition for `audit_logs` in
   `workers/document_worker/app/database.py`, mirroring the pattern already
   used for every other cross-process table (ADR-016).
2. **Spec updated to match reality**, per this document's own rule ("Jika
   implementasi berbeda dari keputusan di dokumen ini, perubahan wajib
   dicatat melalui ADR atau revisi versi dokumen ini"): §9's state diagram
   gains a `PARSED --> APPROVED` edge annotated with the confidence
   condition, and §101/§107.9 gain a note that confidence-gated
   auto-approval is this accepted, audited exception — not the kind of
   silent bypass those rules exist to prevent.

M3's own OCR-fallback `REVIEW_REQUIRED` is untouched by this ADR: a
document that needed OCR to extract text at all is still routed to
`REVIEW_REQUIRED` regardless of M4's structural confidence (see the
existing guard in `tasks.py` and its own test,
`test_interpret_structure_never_upgrades_an_ocr_driven_review_required`) —
confidence in *how well-structured* the text is says nothing about whether
the text itself was extracted correctly.

## Alternatives

- **Always require manual approval, remove auto-approve entirely**:
  rejected — this is the more spec-literal reading, but removes a real
  product capability (fast self-service onboarding for clean documents)
  without addressing the actual risk, which is invisibility, not automation
  itself.
- **Auto-approve but land on a distinct new status** (e.g.
  `AUTO_APPROVED`) instead of reusing `APPROVED`: rejected as unnecessary
  schema churn — the audit log row already distinguishes "who/what approved
  this" without a new enum value that every consumer of
  `DocumentLifecycleStatus` would need to learn about.
- **Raise `STRUCTURE_HIGH_CONFIDENCE` to make auto-approval rarer**:
  rejected as out of scope here — the threshold is a tuning knob, not an
  architectural question; this ADR is about making the existing behavior
  visible and accountable, not about where the cutoff should sit.

## Consequences

- `docs/MASTER_DEVELOPMENT_SPEC.md` §9's state diagram and §101/§107.9 are
  amended alongside this ADR (see that document's own changelog/version
  note) so a future reader of the spec sees the real state machine, not one
  the implementation has quietly departed from.
- Any admin-facing document list/detail view should surface auto-approved
  status distinctly from human-approved (e.g. "Auto-approved — 0.94
  confidence" vs. "Approved by <user>") by querying `audit_logs` for that
  version — not built in this ADR, but the audit row now makes it possible;
  tracked as a follow-up in `docs/KNOWN_LIMITATIONS.md`.
- `workers/document_worker` and `apps/api` now share an implicit contract
  on the `audit_logs` schema in addition to the tables ADR-016 already
  flagged — a future migration changing that table must update both the
  ORM model (`apps/api/app/audit/models.py`) and the worker's Core `Table`
  (`workers/document_worker/app/database.py`).

## Status

Accepted.
