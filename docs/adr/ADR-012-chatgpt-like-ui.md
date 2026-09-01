# ADR-012: ChatGPT-Like Interaction Design (Without Branding)

## Context

End users of a regulatory knowledge assistant are not necessarily technical. A novel or unfamiliar UI paradigm adds cognitive load on top of an already unfamiliar domain (legal/regulatory text). A high proportion of the target audience already has muscle memory from ChatGPT-style chat interfaces (§65).

## Decision

The UI follows ChatGPT's interaction pattern — chat-first, minimal card usage, familiar sidebar + conversation + composer layout (§65-86) — while explicitly not copying Anthropic/OpenAI logos, literal branding, or visual identity (§65). Concretely: a collapsible sidebar (~260px expanded / ~56px collapsed, §67) with New Chat, Search Chats, a "Documents" section replacing the generic "Projects" concept (§68, §108), and grouped chat history (Today/Yesterday/Previous 7 days, §77); a main chat workspace with streaming responses and inline citation chips (§72, §85); and an optional right-hand Source Drawer (~360-420px, §73) for evidence inspection — layout `Sidebar | Chat | Source` (§73).

## Alternatives

- A dashboard/form-heavy "enterprise software" UI (tabs, data tables, explicit query builders) — rejected; higher learning curve, contradicts the "chat-first, minimal card, minimal learning curve" goal (§65).
- A fully novel, from-scratch interaction paradigm — rejected; no research/design budget justification when a familiar pattern already solves the UX goal, and §65 explicitly favors familiarity.

## Reasons

- Familiarity reduces onboarding friction for non-technical regulatory staff — the product goal is self-service, so the interface itself must not be a barrier (§1 items 1, 2).
- The "Documents" sidebar section (not "Projects") reflects that documents are the actual knowledge substrate here, not incidental attachments (§68).

## Consequences

- Frontend component tree (§85) is explicitly speced: `AppShell > Sidebar/ChatWorkspace/SourceDrawer` — new UI work should extend this tree rather than introduce a parallel structure.
- Any UI decision that diverges materially from this interaction model (e.g. a non-chat primary view) is an architecture change requiring its own ADR (§107 rule 2).

## Status

Accepted (frozen decision, spec v1.0, §106).
