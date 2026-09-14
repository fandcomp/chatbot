# ADR-021: Document Visibility Enforcement (PUBLIC/INTERNAL/RESTRICTED)

## Context

`docs/MASTER_DEVELOPMENT_SPEC.md` §7 (Multi-Tenant Architecture) specifies the
mandatory retrieval filter as:

```text
tenant_id = CURRENT_TENANT
AND
knowledge_space_id IN ACTIVE_SPACES
AND
visibility IN USER_ALLOWED_VISIBILITY
AND
document_status = ACTIVE
```

§53 (Document Visibility) defines the three levels and the ordering
constraint:

```text
Level:

PUBLIC
INTERNAL
RESTRICTED

Retriever menerapkan authorization sebelum retrieval.

Tidak boleh:

retrieve confidential
↓
LLM sees it
↓
baru dihapus

Authorization harus terjadi sebelum context dibangun.
```

`visibility` is not a new concept being introduced by this ADR — it is
already a "frozen" (§106) field in §48 (Qdrant payload minimal fields) and
§49 (Qdrant payload index fields), and ADR-002's own Decision section already
states every point "stores the payload defined in §48 (... `visibility`
...)" with indexes "created on the fields listed in §49 (... `visibility`
...)". In practice it was never wired up: `Document`
(`apps/api/app/documents/models.py`) has no `visibility` column,
`workers/document_worker/app/indexing/payload_builder.py`'s own docstring
lists `visibility` as a field "deliberately excluded — no extraction
milestone has ever produced" it, and `RetrievalService.retrieve()`
(`apps/api/app/retrieval/service.py`) filters only on `organization_id`,
optional `knowledge_space_id`, and `document_status == ACTIVE` — it has no
concept of visibility or the requester's role at all.

This is a real gap against §94's "restricted document filtering" and §103's
"Restricted document tidak bocor" (restricted document does not leak)
acceptance criteria, and against CLAUDE.md's Operating Rule 5 ("Never
shortcut tenant isolation") — today, any authenticated org member of any
role, including VIEWER, can have the LLM answer from any ACTIVE document in
the org regardless of sensitivity.

§52 (Authentication & RBAC) defines `OWNER/ADMIN/EDITOR/VIEWER` but — verified
by reading the full spec — never defines what populates `USER_ALLOWED_
VISIBILITY` per role; §6.1's End User "Tidak dapat" list only gestures at
"melihat dokumen restricted tanpa izin" (view a restricted document without
permission) with no elaboration. This ADR has to make that policy decision
explicit, since nothing in the spec or the existing schema does.

## Decision

**Role-based static visibility mapping**, confirmed with the project owner
(no per-document explicit-grant list — see Alternatives):

| Role | Allowed visibility levels |
|---|---|
| VIEWER | PUBLIC |
| EDITOR | PUBLIC, INTERNAL |
| ADMIN, OWNER | PUBLIC, INTERNAL, RESTRICTED |

**Default visibility: PUBLIC**, for both existing documents (via the
migration's `server_default`) and newly-created ones. This preserves current
behavior exactly — every existing document is already visible to every role
today, since no filtering ever existed — matching this codebase's established
least-disruptive-additive-default convention (`source_roots.is_enabled`'s
migration uses the same reasoning for its own `server_default`).

**Enforcement point: filter-before-fetch, in both the Postgres
re-verification path and the Qdrant prefilter** — never a post-hoc filter
applied to already-retrieved results. This is the same pattern ADR-009
already established for tenant/org filtering, and is what §53's "Authorization
harus terjadi sebelum context dibangun" requires. Concretely:

- `RetrievalService.retrieve()` gains a required `allowed_visibilities`
  parameter (resolved by each caller from the role-mapping table above).
- The Postgres queries (`_exact_match`, `_fetch_verified_chunks`) add an
  unconditional join to `Document` and a `Document.visibility.in_(...)`
  clause, alongside the existing `document_status == ACTIVE` clause.
- The Qdrant prefilter (`_tenant_filter`) adds a `visibility` `MatchAny`
  condition, alongside the existing `document_status` condition.
- Every call site of `retrieve()` (`/retrieval/search`, chat, `/reranking/
  evidence`, verification, the "Test Knowledge" escape hatch) is updated to
  pass the requester's allowed set — none of them may bypass it.

**Setting visibility**: a new `PATCH /documents/{document_id}/visibility`
endpoint, gated to `OWNER`/`ADMIN` only (narrower than the `OWNER/ADMIN/
EDITOR` gate used for archive/rollback — setting a document to RESTRICTED is
itself a sensitive action), audit-logged via the existing `log_action`
helper.

## Alternatives

- **Per-document explicit access-grant list** (a `document_access_grants`
  table naming specific `user_id`s allowed to see a RESTRICTED document) —
  closer to a literal reading of §6.1's "tanpa izin" (without permission).
  Rejected for now: nothing in the current schema (`OrganizationMember` has
  only a single org-wide `role` column, no per-user override concept
  anywhere) suggests this granularity is actually needed yet, and it would
  require a whole grant-management UI in addition to the enforcement this
  ADR is scoped to fix. Revisit if a real per-user-grant requirement
  surfaces — the role-based mapping table this ADR introduces is not a
  dead end, it's a strict subset of what a future grant system would need
  to check first anyway.
- **Default new column to `RESTRICTED`** — rejected: this would flip every
  existing document invisible to every VIEWER (and every EDITOR, for
  documents that stay `RESTRICTED`) the moment the migration runs, which is
  a functional regression disguised as a "safe" default, not an additive
  change. `PUBLIC` is the only default that doesn't change any existing
  document's effective visibility today, since no filtering ever existed
  before this ADR.
- **Filter results after retrieval** (fetch normally, then drop
  RESTRICTED/INTERNAL rows the requester isn't allowed to see before
  building the prompt) — explicitly the anti-pattern §53 names and forbids
  ("retrieve confidential → LLM sees it → baru dihapus"). Rejected outright,
  not just as a stylistic preference.

## Consequences

- Existing deployments have an already-created Qdrant `document_chunks`
  collection; `ensure_collection` (`workers/document_worker/app/indexing/
  qdrant_writer.py`) only creates payload indexes the first time the
  collection itself is created, so adding `visibility` to
  `_PAYLOAD_INDEX_FIELDS` alone does **not** retroactively index existing
  deployments. An idempotent create-index call that also runs when the
  collection already exists is added alongside it, so this self-heals
  without a manual one-off script (the LAN-M5 "manual invocation fallback"
  precedent is exactly the failure mode being avoided here).
- The role→visibility mapping is a hardcoded constant, not an
  admin-configurable per-organization setting, until a real need for
  per-org customization is demonstrated (YAGNI).
- Per-document explicit access grants (§6.1's literal "tanpa izin" reading)
  remain unimplemented — explicitly deferred per the Alternatives section
  above, not silently dropped. A future ADR is required before building
  that, per Operating Rule 2.
- Every existing caller of `RetrievalService.retrieve()` requires a
  signature change (new required parameter) — this is a breaking change to
  an internal service method, not a public API, so no deprecation path is
  needed; all call sites are updated in the same change.

## Status

Accepted.
