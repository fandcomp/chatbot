# ADR-002: Qdrant as Vector Store

## Context

The RAG pipeline needs dense vector search over contextual chunk embeddings, combined with structural/sparse signals, and every query must be tenant-scoped (§7) with no possibility of cross-tenant leakage.

## Decision

Qdrant is the vector database. Every point stores the payload defined in §48 (`tenant_id`, `organization_id`, `knowledge_space_id`, `document_id`, `document_version_id`, `document_type/number/year/status`, `visibility`, `node_type`, `chapter/section/article/clause/letter`, `page_start/end`, `sequence_number`, `chunk_id`, `parent_chunk_id`, `index_version`). Payload indexes are created on the fields listed in §49 (`tenant_id`, `organization_id`, `knowledge_space_id`, `document_status`, `visibility`, `document_id`, `article`, `clause`, `document_year`) so every retrieval query can filter before or during the vector search rather than after.

## Alternatives

- pgvector inside PostgreSQL — rejected for this v1.0; Qdrant offers purpose-built payload filtering, HNSW performance, and sparse-vector support without overloading the transactional database.
- A managed vector SaaS with less filtering control — rejected; the mandatory tenant filter (§7) requires first-class payload-level filtering, not post-hoc application-side filtering.

## Reasons

- Native payload filtering makes the mandatory tenant/visibility/status filter (§7) a query-time constraint, not an afterthought — retrieval without a tenant filter is explicitly forbidden (§101).
- Supports both dense and sparse vectors, matching the hybrid retrieval design (ADR-005).

## Consequences

- Every Qdrant query in the codebase must include the mandatory filter block from §7; this is a code-review and security-review checkpoint (see `security-reviewer` agent usage).
- Payload must be kept in sync with PostgreSQL document status changes (archive/delete/supersede) — stale Qdrant points are explicitly disallowed (§57: deleted documents must not be retrievable).

## Status

Accepted (frozen decision, spec v1.0, §106).
