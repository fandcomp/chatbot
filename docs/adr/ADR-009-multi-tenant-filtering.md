# ADR-009: Multi-Tenant Architecture with Mandatory Tenant Filtering

## Context

The platform serves multiple client organizations from shared infrastructure. A single missed filter in one retrieval path could leak one tenant's regulatory documents to another tenant's users.

## Decision

Multi-tenant architecture is foundational from the start (§1 item 14, §7), not retrofitted later. Every important data row carries `organization_id`/`tenant_id` (and `knowledge_space_id`/`chatbot_id` where relevant). Every Qdrant query must apply the mandatory filter block:

```
tenant_id = CURRENT_TENANT
AND knowledge_space_id IN ACTIVE_SPACES
AND visibility IN USER_ALLOWED_VISIBILITY
AND document_status = ACTIVE
```

Tenant isolation is treated as a **security boundary**, not a convenience filter (§7).

## Alternatives

- Single-tenant deployments per client (separate databases/infra per org) — rejected; contradicts the multi-tenant architecture requirement (§1 item 14) and the shared Qdrant/PostgreSQL design (§7-8).
- Application-layer-only filtering (filter results after retrieval instead of during) — rejected; §53 explicitly forbids "retrieve confidential → LLM sees it → baru dihapus" (retrieve-then-filter exposes data to the LLM before removal).

## Reasons

- Filtering at the retrieval/query layer (not post-hoc) ensures the LLM context builder never receives another tenant's or a restricted document's content in the first place (§53-54).
- A single mandatory filter block, applied consistently, is easier to audit and test than scattered per-endpoint authorization logic.

## Consequences

- Any code path that queries Qdrant or PostgreSQL for document/chunk content without applying this filter is a critical security defect — flagged as CRITICAL severity per the security review checklist, and explicitly called out as forbidden (§101 "dilarang retrieval tanpa tenant filter", §107 rule 5).
- Test suite must include tenant isolation as a mandatory test case (§97) for every milestone that touches retrieval.

## Status

Accepted (frozen decision, spec v1.0, §106).
