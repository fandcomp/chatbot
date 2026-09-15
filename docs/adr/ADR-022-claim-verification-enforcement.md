# ADR-022: Enforcing Claim Verification Before Display (Buffer-Then-Verify Streaming)

## Context

ADR-010 (frozen, spec v1.0 §106) mandates: "every claim is checked against
its cited source and marked SUPPORTED/UNSUPPORTED/UNCERTAIN; unsupported
claims are removed or regenerated." A gap audit (2026-09-15) found this was
never actually implemented — `ClaimVerificationService.verify()` computes
the correct status per claim, but nothing ever fed that status back into
what the user is shown. Both `ChatService.answer()` (non-streaming) and
`ChatService.stream_answer()` persist and return the LLM's raw
`summary`/`full_text` unmodified; `verified_claims` is carried only as
side-channel metadata in the API response / SSE `sources` event, which no
frontend code reads (confirmed: `apps/web/src` never consumes
`ClaimStatus`/`.status` on a claim anywhere).

Proof this is a real, exercised gap: `apps/api/tests/integration/
test_verification_answer.py::test_answer_fabricating_pasal_for_numbered_
section_is_flagged_unsupported` feeds a fabricated "Pasal 11" claim for a
source that is provably a numbered section, and asserts the claim's
`status == "UNSUPPORTED"` — but never asserts anything about `summary`,
which still contains the fabricated sentence verbatim. This is exactly the
CLAUDE.md Do-Not: "Let the LLM invent its own citations or determine legal
status itself."

The real complication: `apps/web` only ever calls `POST /chat/stream`
(confirmed — no frontend code references the non-streaming `POST /chat`
at all). `stream_answer()` currently yields each LLM token to the client
**as it arrives**, and only runs `parse_inline_citations` +
`ClaimVerificationService.verify()` on the complete text **after** every
token has already been streamed and displayed. Verification's result
therefore always arrives too late to prevent display in the live chat UI,
regardless of what the enforcement logic does — the bug isn't just "the
status is ignored," it's "the architecture makes it structurally
impossible to act on the status before the user sees the text."

## Decision

**Buffer the full LLM response before streaming anything to the client**,
for `stream_answer()`:

1. Consume the LLM's token stream into `full_text` without yielding any
   `"token"` events during generation (this is the actual architecture
   change — previously incremental, now buffered).
2. Run `parse_inline_citations` + `ClaimVerificationService.verify()` on
   the complete text, exactly as today, but before anything is sent.
3. Redact each `UNSUPPORTED` claim's exact span (its cited text **and**
   its `[S1, S2]` marker, so a fabricated citation is removed too, not
   left dangling) with a visible placeholder — never a silent deletion
   that would leave a broken sentence with no explanation. Spans are
   derived by re-walking the same inline-citation regex over `full_text`,
   not by re-searching for `claim.text` as a substring (fragile —
   `.strip()` and duplicate text would break a substring search; the
   original match objects give exact, unambiguous character offsets).
4. If redaction removes *everything* (every claim in the answer was
   unsupported), replace the whole response with the same
   `_INSUFFICIENT_EVIDENCE_MESSAGE` already used for the empty-evidence
   case, and set `insufficient_evidence: true` — never show a user a wall
   of `[redacted]` placeholders as if that were a real answer.
5. Yield the redacted text to the client in word-sized chunks (no added
   `asyncio.sleep`) so the frontend's existing incremental-append
   rendering still shows a progressive reveal, without stacking artificial
   delay on top of the latency this change already adds.

`ChatService.answer()` (non-streaming) and `POST /verification/answer`
get the coarser fix: since `StructuredAnswer.summary`/`.sections` are
independently LLM-generated fields (not textually derived from
`claims[].text` the way the streaming path's inline-parsed claims are),
there is no reliable character span to redact. If any claim comes back
`UNSUPPORTED`, the whole response is replaced with the insufficient-
evidence shape instead of attempting a substring redaction that could
silently no-op on a paraphrase mismatch. This is safe-by-construction
(fail closed) rather than a parity gap with the streaming path's
surgical redaction — the streaming path can do better because inline
citation markers give it exact spans; the JSON path cannot.

## Alternatives

- **Stream live, send a correction event afterward** (retroactively tell
  the frontend "this span was unsupported" once verification finishes) —
  rejected: the user already read the fabricated text by the time a
  correction could arrive, which does not satisfy ADR-010's "removed...
  before reaching the user." Also requires new frontend UI (strikethrough/
  removal animation) beyond this fix's scope.
- **Leave streaming as-is, only fix the non-streaming path** — rejected:
  `apps/web` never calls the non-streaming path, so this would fix no
  real user-facing behavior at all, only the unused API surface.
- **Ask the LLM for a self-correction pass (regenerate) instead of
  redacting** — ADR-010 explicitly allows this as an alternative to
  removal, but it doubles generation latency (a second full LLM call) for
  a case that redaction already handles safely and near-instantly.
  Deferred; redaction is implemented now, regeneration can be added later
  as a quality improvement without another architecture change (the
  verification step this ADR wires up is the same one a regeneration
  path would need).

## Consequences

- **Latency**: `stream_answer()` no longer shows the first token until
  the entire LLM response has been generated — this is the real trade-off
  ADR-010's own Consequences section flagged ("adds generation latency...
  must be budgeted against §46-47"), now actually paid. The perceived
  "typing" effect is reconstructed client-side from a buffered string, not
  genuine incremental generation.
- A response where every claim is unsupported degrades to the same
  insufficient-evidence shape already used for zero-evidence queries —
  existing frontend handling for that case (per `AssistantMessage.tsx`)
  needs no changes.
- The non-streaming path's coarser "reject the whole answer" behavior is
  intentionally different from the streaming path's surgical redaction —
  documented above, not an oversight.
- `test_verification_answer.py`'s existing UNSUPPORTED-claim test must be
  extended to also assert on `summary`/`insufficient_evidence`, not just
  claim status, or this exact gap could regress silently again.

## Status

Accepted.
