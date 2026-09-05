"""Confidence Check (spec §32/§33) — decides whether M8's reranker runs at
all. Reranking is conditional, never unconditional (spec §101/§47 rule 3).

Skip when M7 already gave a confident answer: a single candidate, or an
EXACT_STRUCTURAL hit confined to one document (e.g. "Pasal 5" plus its own
Ayat chunks from the same regulation — a coherent single-source answer, not
ambiguity). Rerank when the candidate set is genuinely ambiguous: it spans
more than one document — including an EXACT_STRUCTURAL match, since the same
Pasal/angka number existing in two different active regulations is still
ambiguous despite being an "exact" reference type — exceeds the final
evidence count, or the top two candidates are too close in score to trust
ranking order alone.

§33 also lists "complex query" as a rerank trigger — that requires the
multi-query decomposition from §29.3, which M7 does not implement, so it is
not modeled here.
"""

from app.core.config import settings
from app.retrieval.schemas import RetrievalResponse

# Top-2 RRF scores within this fraction of the top score count as
# "berdekatan" (close) — not a spec-given number, a tunable module constant
# (like rrf.py's _DEFAULT_K), not a config knob.
_CLOSE_SCORE_RELATIVE_THRESHOLD = 0.15


def needs_reranking(response: RetrievalResponse) -> bool:
    chunks = response.chunks
    if len(chunks) <= 1:
        return False

    distinct_documents = {chunk.document_id for chunk in chunks}
    if len(distinct_documents) > 1:
        return True

    if response.mode == "EXACT_STRUCTURAL":
        return False

    if len(chunks) > settings.RERANK_TOP_K:
        return True

    top_score, second_score = chunks[0].score, chunks[1].score
    return (
        top_score is not None
        and second_score is not None
        and top_score > 0
        and (top_score - second_score) / top_score < _CLOSE_SCORE_RELATIVE_THRESHOLD
    )
