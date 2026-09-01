# ADR-010: Evidence-First Generation Pipeline

## Context

An LLM asked a legal/regulatory question will happily answer from its own training knowledge and then, if pressed, invent a plausible-looking citation to match. For a regulatory assistant this is unacceptable: a wrong article number, a hallucinated sanction, or a fabricated "no such rule exists" answer carries real consequences for the client.

## Decision

The system enforces a strict pipeline order (§3.1):

```
QUESTION → RETRIEVAL → EVIDENCE → VALIDATION → GENERATION → CLAIM CHECK → CITATION → ANSWER
```

Never the inverse (`QUESTION → LLM KNOWLEDGE → ANSWER → find citation afterward`). The LLM is explicitly **not** the source of truth — the client's active documents are (§3.1). The system is forbidden from inventing regulation numbers, document titles, article/clause/letter numbers, dates, sanctions, requirements, authority, procedures, legal basis, or legal status (§3.2). When evidence is insufficient, the system must say so with a specific phrase ("the information has not been found in the currently available documents") rather than the stronger, unsupported claim "there is no rule about this" (§3.2) — the two are not equivalent and conflating them is itself a hallucination risk.

Generation output is structured (Pydantic-validated JSON, §38) and passes through claim verification (§40) and citation validation (§41) before reaching the user — every claim is checked against its cited source and marked SUPPORTED/UNSUPPORTED/UNCERTAIN; unsupported claims are removed or regenerated.

## Alternatives

- Generate-then-cite (ask the LLM to answer, then separately ask it to find supporting quotes) — rejected; this is exactly the forbidden inverse pipeline (§3.1) and is why the ADR exists.
- Trusting model self-reported confidence/citations without a separate validation pass — rejected; LLMs are not reliable judges of their own factual grounding, hence the explicit claim-check + citation-validation stages (§40-41) as independent steps.

## Reasons

- Retrieval-before-generation guarantees the model only ever sees real document text (the evidence pack, §39) as its source material, structurally reducing (not eliminating) hallucination surface area.
- A separate claim-verification pass catches the residual cases where the model still drifts from its provided evidence during generation.
- Distinguishing "not found" from "does not exist" (§3.2) preserves user trust — the system should never claim authority it doesn't have over what regulations exist.

## Consequences

- Every new answer-generation code path must be evaluated against this pipeline order before merge; skipping evidence/validation/claim-check steps to "simplify" a code path is an architecture change requiring its own ADR (§107 rule 2).
- Adds generation latency (extra verification pass) that must be budgeted against the latency targets in §46-47.

## Status

Accepted (frozen decision, spec v1.0, §106).
