# ADR-011: Server-Sent Events for Response Streaming

## Context

Regulatory answers can be long (multi-item lists, multi-source comparisons) and the retrieval+generation pipeline (parse → retrieve → rerank → evidence → LLM) has several sequential stages before the first token is available. Without streaming, users stare at a blank composer for the full pipeline latency; the spec's own latency targets (§46) call for a perceived time-to-first-token around ~1s and p95 under 2s, which is only achievable if partial output starts rendering before the full answer is generated.

## Decision

Streaming is mandatory (§4, §47 rule 1: "Streaming wajib"), implemented via Server-Sent Events (SSE) over a dedicated `POST /chat/stream` endpoint (§87). The frontend renders tokens incrementally as they arrive rather than waiting for the complete structured response.

## Alternatives

- WebSockets — rejected; SSE is simpler for the one-directional server→client token stream this use case needs (no bidirectional messaging required mid-answer), has native browser `EventSource` support, and plays more simply with standard HTTP infrastructure (load balancers, proxies) than a persistent bidirectional socket.
- Long-polling — rejected; higher latency and overhead per chunk than a single open SSE connection, and offers no advantage here since there is no need for the client to poll on its own schedule.
- No streaming (wait for full answer) — rejected; directly violates §47 rule 1 and would blow the p95 TTFT < 2s target (§46) for any non-trivial answer.

## Reasons

- SSE gives incremental perceived latency improvements matching the ChatGPT-like interaction model the UI is built around (§65, ADR-012).
- Simpler infra/client requirements than WebSockets for a purely server-to-client token stream.

## Consequences

- Backend generation code (both Fast and Strong LLM paths, §34) must support streaming-compatible output from the LLMGateway (§35) rather than only batch `generate()`.
- Claim verification and citation validation (§40-41, ADR-010) must be designed to work incrementally or as a final validation pass over the streamed-then-assembled answer — this interaction needs explicit handling in the chat service, not an afterthought.

## Status

Accepted (frozen decision, spec v1.0, §106).
