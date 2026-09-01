# ADR-008: Voyage Context-4 Embedding + Voyage rerank-2.5-lite (Conditional)

## Context

Dense retrieval quality depends heavily on embedding quality, and reranking every query unconditionally adds latency that the performance targets (§46-47) cannot always afford.

## Decision

Voyage Context-4 is the embedding model, accessed through an `EmbeddingGateway` interface (§36). Voyage rerank-2.5-lite is the reranker, accessed through a `RerankerGateway` interface (§37), invoked **conditionally** — skipped for exact Pasal/Ayat matches, very high structural confidence, very clear evidence, or a single valid source; used for many candidates, semantic ambiguity, close top scores, multi-document queries, or complex queries (§33).

## Alternatives

- Reranking every query unconditionally — rejected explicitly (§101 "dilarang rerank semua query tanpa condition").
- A generic/open embedding model instead of Voyage Context-4 — not chosen; Voyage's contextual embedding is the named decision (§4, §36).

## Reasons

- Contextual embedding (embedding text alongside its document/BAB/Pasal/Ayat context, §24.2) improves retrieval precision for structurally nested legal text over embedding raw text alone.
- Conditional reranking directly serves the latency budget (§46: reranking budgeted at 100-400ms only when it runs) and the "deterministic before LLM/expensive-step" principle (§3.4) extended to reranking.

## Consequences

- Both gateways must be implemented as swappable interfaces (per ADR-007's gateway pattern) even though only one provider is named today — provider neutrality (§3.5) applies to embedding/reranking too.
- The condition logic for skip-vs-rerank (§33) is itself a piece of business logic that needs test coverage, since getting it wrong either hurts recall (skipping when needed) or latency (reranking when unnecessary).

## Status

Accepted (frozen decision, spec v1.0, §106).
