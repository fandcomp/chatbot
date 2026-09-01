# ADR-006: Structure-First Hierarchical Chunking

## Context

Regulatory documents have meaningful internal structure (BAB, Bagian, Pasal, Ayat, Huruf) that carries legal significance — splitting a Pasal mid-sentence at an arbitrary token boundary destroys the unit of meaning a citation needs to point to.

## Decision

Chunking priority is legal/document structure first, semantic structure second, token limit last (§3.3, §22). A short Pasal becomes one chunk; a long Pasal becomes a parent chunk with one child chunk per Ayat; only an individual Ayat that is itself too long falls back to semantic/token subdivision (§22). Parent/child/previous/next relationships are tracked explicitly (§23).

## Alternatives

- Fixed-size token chunking (e.g. flat 500-token windows) as the primary strategy — rejected explicitly (§101 "dilarang fixed-size chunking sebagai strategi utama", §909 "Jangan fixed 500-token chunking sebagai metode utama").
- Pure semantic chunking (embedding-similarity boundaries) — rejected as primary; used only as a last-resort subdivision within an oversized structural unit.

## Reasons

- Citations must resolve to a specific Pasal/Ayat/Huruf (§27 provenance chain) — chunk boundaries that don't respect structure make accurate citation impossible.
- Structure-aware chunks also make exact-reference retrieval (§29.1) a direct lookup rather than a search problem.

## Consequences

- Chunking depends on the regulatory structure layer (§15-17) succeeding with sufficient confidence; low-confidence structure falls back to the Generic Document Tree (§14), which still enables (coarser) structure-first chunking at the Section/Paragraph level rather than falling all the way back to fixed-size windows.
- Neighbor expansion (§23) must be used selectively ("jika relevan"), not unconditionally, to avoid bloating context.

## Status

Accepted (frozen decision, spec v1.0, §106).
