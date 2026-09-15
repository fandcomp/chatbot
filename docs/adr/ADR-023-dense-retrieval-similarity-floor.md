# ADR-023: A Cosine-Similarity Floor on Dense Retrieval Only

## Context

A gap audit (2026-09-15) of the evidence/citation/verification chain found
that no relevance-score floor exists anywhere between retrieval and
generation. `RerankingService.select_evidence` always takes the top
`RERANK_TOP_K` candidates regardless of any absolute quality measure, and
`RetrievalService`'s Qdrant queries pass no `score_threshold`. The gap is
sharpest in `needs_reranking()`'s "skip reranking" branch
(`apps/api/app/reranking/confidence.py`): a single-document hybrid result
whose top RRF score merely dominates the runner-up (a *relative* check) is
trusted as-is, with no check that the top result is *absolutely* any good.
A weakly-matching or off-topic query can therefore still produce "evidence"
that reaches the LLM as if authoritative, instead of correctly triggering
insufficient-evidence.

The complication that makes this harder than "just add a threshold":
relevance is expressed on three genuinely different, non-comparable
scales in this pipeline —

1. **EXACT_STRUCTURAL matches** carry no score at all (`RetrievedChunk.
   score = None`) — trusted by construction (a parsed legal reference
   matched a real article/clause number), not a candidate for a numeric
   floor.
2. **RRF fusion scores** (`apps/api/app/retrieval/rrf.py`) are a
   reciprocal-rank sum across the dense and sparse rankings — a relative,
   rank-derived number with no absolute "this is relevant" meaning. A
   fixed numeric floor on this scale would be arbitrary, not principled.
3. **Voyage rerank scores** (0-1, genuinely comparable) only exist when
   reranking actually ran — which spec §101/§47 rule 3 explicitly
   forbids making unconditional ("reranking conditional, never
   unconditional"). Flooring only on this scale would leave the exact
   branch the audit found unprotected, since that branch is defined by
   reranking having been *skipped*.

Within the two Qdrant queries that feed RRF fusion, the **dense** arm
(cosine similarity, `models.Distance.COSINE`) is the one scale in this
whole pipeline that is both universal (every embedding pair has a
well-defined cosine similarity) and available before RRF fusion discards
that information. The **sparse** arm's IDF-weighted score has no such
universal reading — a sparse hit already shares at least one term with
the query by construction (that's how sparse vector search matches at
all), so its score reflects term rarity/frequency, not a fixed relevance
scale a single default could reasonably threshold.

## Decision

Add `settings.DENSE_SIMILARITY_FLOOR` (default `0.2`) and pass it as
`score_threshold` on the **dense** `query_points` call only, in
`RetrievalService._hybrid_search`. The sparse query gets no threshold.

The default is deliberately permissive — it excludes only candidates
whose cosine similarity is near zero or negative (i.e., not meaningfully
related to the query at all), not a strict "must be highly relevant"
cutoff. This is a conscious choice given spec §102's Priority Order ranks
"correct retrieval" above "security": a threshold chosen without real
production query data to calibrate against risks rejecting legitimate
borderline queries (a retrieval-correctness regression) in exchange for
closing a gap that, absent real incident data, is a theoretical risk. The
mechanism (an actual floor, applied where it can be principled) is what
this ADR establishes; the specific value is explicitly a starting point,
not a benchmarked constant — same posture the LAN-M6 track already
recorded for its own benchmarking work that has no real data to run
against in this dev environment.

## Alternatives

- **Floor the RRF fused score directly** — rejected: it's a rank-derived
  relative number, not a stable relevance measure; the same absolute
  relevance could produce different RRF scores depending on how many
  other candidates existed and their own scores.
- **Always rerank (remove the "skip when not close" branch)** — would
  guarantee a real Voyage score on every hybrid query, but directly
  contradicts spec §101/§47 rule 3's explicit "never unconditional"
  rule. Rejected as a spec violation, not a design preference.
- **Floor the Voyage rerank score, only when reranking runs** — a real
  option, and not mutually exclusive with this decision, but does not
  close the specific gap the audit found (the skip-rerank branch, by
  definition, never produces a Voyage score to floor). Left as a
  possible future addition, not a substitute for this ADR's fix.
- **Also floor the sparse arm with some default** — rejected for now:
  no principled universal value exists without corpus-specific
  calibration (document length, vocabulary, and IDF distribution all
  shift what a "good" sparse score looks like). Revisit if real query
  data ever becomes available to calibrate against.

## Consequences

- Dense-arm candidates below the floor are silently excluded from the
  candidate set that reaches RRF fusion — a query that only weakly
  matches everything in the knowledge base is now more likely to
  correctly reach insufficient-evidence instead of citing a barely
  related chunk as if it answered the question.
- The sparse arm is unchanged — this ADR closes part of the gap, not
  all of it. A candidate that scores well on sparse/keyword overlap
  alone but poorly on dense similarity can still surface; that's an
  accepted, explicitly scoped-out limitation, not an oversight.
- `DENSE_SIMILARITY_FLOOR` is a new tunable that should be revisited
  once real production query/retrieval-quality data exists — recorded
  in this session's memory, per the same pattern used for every other
  "not yet benchmarked" value in this codebase.

## Status

Accepted.
