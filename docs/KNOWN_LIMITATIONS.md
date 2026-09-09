# Known Limitations

Deliberate, already-scoped-down behaviors and follow-up items surfaced by
the 2026-09 M15 hardening pass, kept here so they are visible instead of
only living in code comments. Each entry names where to look and what
would trigger picking it back up.

## LLM inline-citation format compliance (observed, not yet fixed)

While building the e2e golden path (above), the real configured model
(GPT-OSS via Groq) was observed citing with the source's structural path
directly — `"...tata tertib kantor. [BAB I > Pasal 1]"` — instead of the
`[S1]`-style source-id marker `app/chat/inline_citation_parser.py`'s
`_MARKER_RE` expects (spec §41, ADR-010). This means
`CitationChip`/`render-citations.tsx` never rendered a clickable inline
citation for that turn even though a real, correct citation existed in the
`sources` SSE event (`AdaptiveCitationService` built it correctly) — the
answer text itself was accurate, only the inline marker format diverged
from the system prompt's instruction. Single observation, not a
statistically characterized failure rate. *Revisit by:* checking
`app/llm/context_builder.py`'s (or wherever the citation-format instruction
lives) prompt wording for ambiguity, and/or widening
`inline_citation_parser.py`'s `_MARKER_RE` to also recognize a bracketed
structural-path fallback — but only after collecting more real samples
(e.g. via `tests/rag_eval/evaluate.py`'s `citation_accuracy` metric over a
real dataset) to know whether this is common enough to warrant either fix.

## Worker structural-interpretation limitations

All four of these are already called out as intentional first-pass scope
decisions in their own code comments (not bugs) — listed centrally here so
they don't get lost until a real regulatory PDF actually needs the fix.

- **Grammar detected per `StructuralRegion`, not per node**
  (`workers/document_worker/app/interpretation/pattern_detector.py:1-5`). A
  stray non-conforming node inside an otherwise-consistent region is never
  individually promoted. *Revisit if:* a real document is found with mixed
  grammar inside a single region (e.g. one Pasal-numbered paragraph dropped
  into an otherwise numbered-list BAB).
- **Flat-sibling list clustering** (`.../interpretation/specialized_interpreter.py:6-12`).
  Docling's flat tree can place list items like "11.", "a.", "b.", "12." as
  siblings instead of nesting "a."/"b." under "11." — partially mitigated by
  commit `b10918f` ("recover legal-structure hierarchy... from flat
  siblings"), but the interpreter's own comment still describes this as a
  known layout-clustering limitation. *Revisit if:* a real document
  surfaces a flat-sibling pattern the current recovery heuristic doesn't
  catch.
- **Numbering-gap confidence tracked per `node_type` per region, not per-parent**
  (`.../interpretation/confidence.py:6-10`), e.g. per-chapter. *Revisit if:*
  confidence scores are found to be misleading on a document with several
  chapters of differing numbering quality.
- **A single run-on "sentence" with no punctuation is left as one oversized chunk**
  (`.../chunking/chunk_builder.py:203-209`) rather than raising. *Revisit
  if:* oversized chunks are observed degrading retrieval/rerank quality in
  practice.

## RAG evaluation harness

`tests/rag_eval/evaluate.py` computes Recall@K, MRR, nDCG, Citation
Accuracy/Coverage, Insufficient-Evidence Accuracy, latency (p50/p95), and
Cost per Query (spec §96). It deliberately does **not** compute
**Faithfulness** or **Answer Correctness** — both need an LLM-as-judge
harness (a second LLM call scoring the generated answer against evidence/a
golden answer), which is new infrastructure, not a mechanical addition to
the existing evaluator. Building it speculatively without a real evaluation
dataset first would be premature. *Revisit when:* a real golden dataset
(`tests/rag_eval/dataset.json`) exists with enough volume to make an
LLM-judge score worth the added cost and complexity.

## Cross-app e2e coverage

`tests/e2e/` (Playwright) currently covers one golden path: login → ask a
question against a `seed.py`-seeded ACTIVE document (real Docling parse +
real Voyage embeddings, run once per test invocation) → verify the
streamed answer is grounded in that document's real text and the SSE
response's `sources` event carries a real citation. It does **not** cover
the full upload → parse → review → approve → publish pipeline end-to-end
through the UI — `seed.py` reaches ACTIVE via the API directly (no manual
review click), and is too slow/flaky for a routine e2e run to also drive
through upload UI + polling UI + approve UI. *Revisit when:* the project
wants CI-gated confidence in the full document lifecycle UI, at which point
it should likely run on a slower, separate schedule rather than every PR.

It also does **not** assert on the rendered inline citation chip (`[S1]` in
the chat bubble) — see `tests/e2e/README.md`'s explanation of why that's a
deliberate choice, not a gap: real LLM output doesn't always follow the
exact citation-marker format the chip's rendering depends on, and that's a
model-prompt-adherence concern, not something this e2e test should grade.

## Shared frontend/backend types

`packages/schemas` now generates `src/api-types.ts` from the FastAPI
OpenAPI schema (see its README) as a proof of concept, adopted so far only
for the document-relations types. The rest of `apps/web`'s hand-written Zod
schemas have **not** been migrated — that's a larger, separate effort
(each migration needs to verify the generated type and the hand-written
Zod schema actually agree on runtime validation, not just shape) and is
out of scope for this hardening pass. *Revisit incrementally*, migrating a
domain's types the next time that domain's schemas need to change anyway.

## Demo tunnel account (verified, no action needed)

`scripts/start-demo-tunnel.sh` prints a reminder that the demo login
(`client-demo@analytics-demo.io`) should be VIEWER-role. Confirmed by
2026-09 audit: `VIEWER` is already the most-restrictive `OrgRole` in the
system and is enforced server-side via `require_role` on every
write/admin endpoint (see `apps/api/tests/unit/test_document_relations_rbac.py`'s
`test_viewer_cannot_create_a_relation` and equivalents across the RBAC test
suite) — there is no seed script that could hardcode a wrong role for this
account; it's created manually by whoever runs a demo, and the worst case
of choosing the wrong role at creation time is still bounded by the same
RBAC enforcement every other user goes through.
