# ADR-004: No GraphRAG, No Neo4j

## Context

Regulatory documents do have relationships to each other (amends, repeals, replaces, implements, refers to, superseded by — §21) and internally have a natural hierarchy (BAB → Bagian → Pasal → Ayat → Huruf — §15). GraphRAG/graph databases are a common approach to modeling this kind of structure.

## Decision

The system explicitly does not use GraphRAG or Neo4j anywhere in the pipeline (§1 item 12, §28 "Tidak ada GraphRAG", §101, §106). Document-to-document relationships are stored as plain relational rows in PostgreSQL (§21); intra-document hierarchy is captured via parent/child chunk pointers and structural metadata (§22-23), not a graph traversal engine.

## Alternatives

- GraphRAG with multi-hop relationship reasoning over a knowledge graph — rejected.
- Neo4j (or any graph database) as a secondary store for document relationships — rejected; explicitly named as unnecessary (§21 "Tidak perlu Neo4j").

## Reasons

- The relationship types needed (AMENDS, REPEALS, REPLACES, IMPLEMENTS, REFERS_TO, SUPERSEDED_BY) are low-cardinality and directly queryable via SQL joins — no multi-hop graph reasoning is required by any use case in this spec.
- Avoids operating a second database technology, a second query language, and a second consistency model, for a capability PostgreSQL already covers.
- Keeps the "Final RAG Type" (§28) — Adaptive Structure-Aware Contextual Hybrid RAG — free of a dependency that adds infrastructure cost without a corresponding requirement.

## Consequences

- Any future requirement for genuine multi-hop relationship reasoning (e.g. "trace all regulations amended by regulations that amend Regulation X") would require revisiting this ADR, not silently bolting on a graph layer.
- Relationship data must be actively maintained by admins/ingestion (§21) since there is no automatic graph inference.

## Status

Accepted (frozen decision, spec v1.0, §106). Adding GraphRAG/Neo4j without superseding this ADR is a violation of the development operating rule (§107 rule 6).
