"""ClaimVerificationService (spec §90/§40) — Answer -> Claims -> Source
Mapping -> Support Check. Deterministic Tier-0 checks only, no extra LLM
call (see this milestone's design decision):

1. Every source_id a claim cites must exist among the evidence actually
   provided — directly enforces spec §101's "LLM tidak boleh membuat
   citation sendiri".
2. Addendum §34's terminology-mismatch rule: a claim that says "Pasal N"
   is invalid unless at least one cited source's own Structural Path
   (rendered adaptively by M5 using the source's real terminology) uses
   that word — never a fabricated Pasal for a numbered-section-only source.
3. A lexical-overlap heuristic between claim text and cited evidence as a
   cheap proxy for semantic support — SUPPORTED above threshold, UNCERTAIN
   below it, never confidently SUPPORTED on weak overlap.
"""

import re

from app.llm.answer_schemas import Claim
from app.reranking.schemas import Evidence
from app.verification.schemas import ClaimStatus, VerifiedClaim

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_PASAL_MENTION_RE = re.compile(r"\bpasal\s+\d+", re.IGNORECASE)
_MIN_TOKEN_LENGTH = 4
_OVERLAP_SUPPORTED_THRESHOLD = 0.3


def _significant_tokens(text: str) -> set[str]:
    return {token.lower() for token in _WORD_RE.findall(text) if len(token) >= _MIN_TOKEN_LENGTH}


class ClaimVerificationService:
    def verify(self, claims: list[Claim], evidence: list[Evidence]) -> list[VerifiedClaim]:
        evidence_by_id = {item.evidence_id: item for item in evidence}
        return [self._verify_claim(claim, evidence_by_id) for claim in claims]

    def _verify_claim(
        self, claim: Claim, evidence_by_id: dict[str, Evidence]
    ) -> VerifiedClaim:
        unknown_ids = [sid for sid in claim.source_ids if sid not in evidence_by_id]
        if unknown_ids or not claim.source_ids:
            return VerifiedClaim(
                text=claim.text,
                source_ids=claim.source_ids,
                status=ClaimStatus.UNSUPPORTED,
                invalid_reason=(
                    f"cites unknown source id(s): {', '.join(unknown_ids)}"
                    if unknown_ids
                    else "cites no source id"
                ),
            )

        cited = [evidence_by_id[sid] for sid in claim.source_ids]

        if _PASAL_MENTION_RE.search(claim.text):
            any_article_source = any(
                item.structural_path_text and "pasal" in item.structural_path_text.lower()
                for item in cited
            )
            if not any_article_source:
                return VerifiedClaim(
                    text=claim.text,
                    source_ids=claim.source_ids,
                    status=ClaimStatus.UNSUPPORTED,
                    invalid_reason=(
                        "claim references 'Pasal' but none of the cited sources' "
                        "Structural Path uses that terminology (addendum §34)"
                    ),
                )

        claim_tokens = _significant_tokens(claim.text)
        if not claim_tokens:
            return VerifiedClaim(
                text=claim.text, source_ids=claim.source_ids, status=ClaimStatus.UNCERTAIN,
                invalid_reason=None,
            )

        evidence_tokens: set[str] = set()
        for item in cited:
            evidence_tokens |= _significant_tokens(item.original_text)

        overlap_ratio = len(claim_tokens & evidence_tokens) / len(claim_tokens)
        status = (
            ClaimStatus.SUPPORTED
            if overlap_ratio >= _OVERLAP_SUPPORTED_THRESHOLD
            else ClaimStatus.UNCERTAIN
        )
        return VerifiedClaim(
            text=claim.text, source_ids=claim.source_ids, status=status, invalid_reason=None
        )
