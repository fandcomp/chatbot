# ADR-001: PostgreSQL as Source of Truth

## Context

The system needs an authoritative store for organizations, users, documents, document versions, chunks, conversations, messages, and all relational metadata (§50-51 core tables). Document validity/legal status (§20) and inter-document relationships such as AMENDS/REPEALS/SUPERSEDES (§21) must be queryable and consistent, and every retrieval must be filterable by tenant, knowledge space, and visibility (§7).

## Decision

PostgreSQL is the system of record for all structured data: organizations, users, memberships, knowledge spaces, documents, document versions, document nodes, chunks metadata, processing jobs, conversations, messages, citations, audit logs, and analytics. Qdrant holds only vectors + a payload mirror for retrieval filtering (see ADR-002); it is never the source of truth for document status or relationships.

## Alternatives

- A graph database (Neo4j) for document relationships — rejected, see ADR-004.
- Storing binary documents in PostgreSQL — rejected; originals live in S3/MinIO (§55), PostgreSQL stores paths/metadata only.
- Using Qdrant payload as the primary metadata store — rejected; Qdrant is a vector index, not a transactional relational store, and cannot enforce foreign keys, tenant constraints, or ACID guarantees needed for approval/publish workflows (§9-10).

## Reasons

- Document relationships (§21: AMENDS, REPEALS, REPLACES, IMPLEMENTS, REFERS_TO, SUPERSEDED_BY) are naturally relational and low-cardinality — no graph traversal engine is needed.
- Document lifecycle (§9 state machine) and multi-tenant access control (§7, §52-53) require transactional guarantees.
- Enables standard relational tooling: Alembic migrations, foreign-key integrity, indexing on `tenant_id`/`document_status`/`article`/`clause` (§49).

## Consequences

- All mandatory tenant filters (§7) must be enforced at the PostgreSQL/query-builder layer, not just in Qdrant.
- Cross-document relationship queries stay simple SQL joins rather than graph traversals — acceptable because the spec explicitly does not require multi-hop relationship reasoning (§21, §106 "Tidak perlu Neo4j").
- Requires careful indexing (§49) as document/chunk volume grows, since PostgreSQL also backs exact legal reference lookup (§29.1).

## Status

Accepted (frozen decision, spec v1.0, §106).
