# ADR-007: Hugging Face Inference Providers as LLM Gateway

## Context

The system must remain provider-neutral (§3.5) — business logic must never hardcode a specific LLM vendor SDK — while still routing between a fast, cheap model for the majority of queries and a strong model for complex ones (§34).

## Decision

All LLM calls go through a single `LLMGateway` interface (§35) backed by Hugging Face Inference Providers. The fast path uses GPT-OSS 20B via Groq; the strong path uses GPT-OSS 120B via Groq (§34.2-34.3). Fallback to an alternative provider through Hugging Face is used only on timeout, rate limit, or provider error (§34.4) — not as a load-balancing default.

## Alternatives

- Calling Groq (or any provider) directly from business services — rejected explicitly (§101 "dilarang hardcode provider pada business service", §3.5).
- A single model tier for all queries — rejected; §34 requires complexity-based routing (Tier 0 no-LLM, Fast, Strong) to control latency and cost (§47 rule 10-11).
- Local/self-hosted LLM — rejected explicitly (§1 item 11 "Menggunakan cloud LLM, tanpa local LLM", §101, §106).
- Fine-tuning as the mechanism for injecting domain knowledge — rejected explicitly (§1 item 13, §101, §106); knowledge enters the system only through the RAG ingestion pipeline.

## Reasons

- A gateway interface (`generate`, `generate_structured`, `stream`) lets the fast/strong/fallback model routing change without touching any calling code.
- Routing complexity to a Tier 0 (no LLM at all — regex/metadata/exact lookup, §3.4, §34.1) before ever reaching Fast/Strong keeps deterministic problems out of the LLM entirely.

## Consequences

- Every LLM call site must go through `LLMGateway`, never a provider SDK — this is a security-reviewer/code-reviewer checkpoint.
- Model routing logic (query complexity classification) becomes its own maintained component (§34), separate from generation itself.

## Status

Accepted (frozen decision, spec v1.0, §106).
