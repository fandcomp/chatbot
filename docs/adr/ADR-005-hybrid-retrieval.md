# ADR-005: Hybrid Retrieval (Dense + Sparse + RRF)

## Context

Regulatory queries range from exact structural lookups ("Pasal 17 ayat 2") to natural-language semantic questions, and often mix legal terminology, identifiers, and abbreviations that pure semantic search misses.

## Decision

Retrieval combines dense semantic search (contextual embeddings) and sparse lexical search (BM25/sparse vectors) in parallel, fused via Reciprocal Rank Fusion (§29.2, §32). Exact legal references bypass vector search entirely and go straight to structural/metadata lookup (§29.1) — never vector-first for an exact reference.

## Alternatives

- Semantic-only (dense) search — rejected explicitly (§101 "dilarang semantic search saja"); dense search alone misses exact identifiers, numbers, and legal phrases that sparse/lexical matching catches (§29.2).
- Regex/exact-match only — rejected explicitly (§101 "dilarang regex saja"); natural-language queries need semantic understanding.
- LLM-based query rewriting for every query — rejected (§47 latency rule 4, §101); adds latency and cost without benefit for queries that don't need it.

## Reasons

- Dense search captures meaning; sparse search catches terms, identifiers, numbers, abbreviations, and legal phrases (§29.2) — the two are complementary, not substitutable.
- RRF is a simple, well-understood, parameter-light fusion method that doesn't require training a learned fusion model.
- Exact-reference short-circuiting (§29.1, §3.4 "Deterministic Before LLM") avoids unnecessary vector search and LLM calls for a class of query that has a deterministic answer.

## Consequences

- The query router (§32) must correctly classify exact-reference vs. natural-language queries before choosing a retrieval path — misclassification degrades either latency (unnecessary hybrid search) or recall (missed exact match).
- Both a dense index (Qdrant) and a sparse representation must be maintained and kept in sync at indexing time (§28).

## Status

Accepted (frozen decision, spec v1.0, §106).
