"""Parses a streamed answer's inline "...text [S1, S2]" citation markers
back into the same Claim{text, source_ids} shape generate_structured
would have produced (spec §41's S1/S2 labels), so
app/verification/service.py's ClaimVerificationService needs no
streaming-specific variant.

A trailing segment with no marker at all becomes a claim with an empty
source_ids list — ClaimVerificationService already treats "cites no source"
as UNSUPPORTED, which is the correct outcome for an uncited assertion.
"""

import re

from app.llm.answer_schemas import Claim

_MARKER_RE = re.compile(r"(.+?)\[\s*((?:S\d+\s*,?\s*)+)\]", re.DOTALL)
_LABEL_RE = re.compile(r"S\d+")


def parse_inline_citations(text: str) -> list[Claim]:
    claims: list[Claim] = []
    last_end = 0

    for match in _MARKER_RE.finditer(text):
        segment_text = match.group(1).strip()
        last_end = match.end()
        if not segment_text:
            continue
        source_ids = _LABEL_RE.findall(match.group(2))
        claims.append(Claim(text=segment_text, source_ids=source_ids))

    trailing = text[last_end:].strip()
    if trailing:
        claims.append(Claim(text=trailing, source_ids=[]))

    return claims
