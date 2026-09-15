"""Parses a streamed answer's inline "...text [S1, S2]" citation markers
back into the same Claim{text, source_ids} shape generate_structured
would have produced (spec §41's S1/S2 labels), so
app/verification/service.py's ClaimVerificationService needs no
streaming-specific variant.

A trailing segment with no marker at all becomes a claim with an empty
source_ids list — ClaimVerificationService already treats "cites no source"
as UNSUPPORTED, which is the correct outcome for an uncited assertion.

ADR-022 also uses this module's span-walking (`_iter_claim_spans`) to
redact UNSUPPORTED claims from the final text before it ever reaches a
user — see `redact_unsupported_claims` below.
"""

import re

from app.llm.answer_schemas import Claim
from app.verification.schemas import ClaimStatus, VerifiedClaim

_MARKER_RE = re.compile(r"(.+?)\[\s*((?:S\d+\s*,?\s*)+)\]", re.DOTALL)
_LABEL_RE = re.compile(r"S\d+")

# ADR-022: a redacted claim is replaced, never silently deleted — a missing
# sentence with no explanation reads as a rendering bug, not a safety
# control working as intended.
REDACTION_PLACEHOLDER = (
    "[Pernyataan ini dihapus karena tidak dapat diverifikasi terhadap "
    "dokumen yang tersedia.]"
)


def _iter_claim_spans(text: str) -> list[tuple[str, list[str], tuple[int, int]]]:
    """Yields (segment_text, source_ids, (start, end)) for each inline-cited
    segment in document order. `(start, end)` spans the segment's exact
    characters INCLUDING its trailing `[S1, S2]` marker for a cited
    segment, so redacting it also removes the (possibly fabricated)
    citation marker itself, not just the prose — or just the segment's own
    characters for an unmarked trailing segment, which has no marker to
    include.

    `parse_inline_citations` and `redact_unsupported_claims` both build on
    this single walk so there is exactly one place that defines "how this
    text splits into claims," never two independently-maintained copies of
    the same regex logic that could drift apart.
    """
    results: list[tuple[str, list[str], tuple[int, int]]] = []
    last_end = 0

    for match in _MARKER_RE.finditer(text):
        segment_text = match.group(1).strip()
        last_end = match.end()
        if not segment_text:
            continue
        source_ids = _LABEL_RE.findall(match.group(2))
        results.append((segment_text, source_ids, (match.start(), match.end())))

    trailing = text[last_end:].strip()
    if trailing:
        results.append((trailing, [], (last_end, len(text))))

    return results


def parse_inline_citations(text: str) -> list[Claim]:
    return [Claim(text=t, source_ids=ids) for t, ids, _span in _iter_claim_spans(text)]


def redact_unsupported_claims(text: str, verified_claims: list[VerifiedClaim]) -> str:
    """ADR-022: replaces each UNSUPPORTED claim's exact span (re-derived by
    re-walking `text`, never by re-searching for `claim.text` as a
    substring — `.strip()` and duplicate/repeated text would make a
    substring search ambiguous or wrong) with `REDACTION_PLACEHOLDER`.

    `verified_claims` must be the direct result of verifying
    `parse_inline_citations(text)` against the same `text` — if re-walking
    `text` here produces a different number of spans than `verified_claims`
    has entries, something upstream changed between the two calls. Rather
    than guess which claim maps to which span, this returns `text`
    unmodified — silently redacting the wrong span would be worse than not
    redacting at all.
    """
    spans = _iter_claim_spans(text)
    if len(spans) != len(verified_claims):
        return text

    pieces: list[str] = []
    cursor = 0
    for (_segment_text, _source_ids, (start, end)), verified in zip(spans, verified_claims):
        pieces.append(text[cursor:start])
        pieces.append(
            REDACTION_PLACEHOLDER if verified.status == ClaimStatus.UNSUPPORTED else text[start:end]
        )
        cursor = end
    pieces.append(text[cursor:])

    return "".join(pieces)
