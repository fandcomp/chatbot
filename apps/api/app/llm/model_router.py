"""Model Complexity Router (spec §34.2-34.3) — chooses Fast vs Strong
without ever calling an LLM to decide (§47 rules 4-5's no-extra-LLM-call
spirit): a regex/heuristic classifier, Tier-0-style, same philosophy as
app/retrieval/query_parser.py.

Tier 0 (no LLM at all) is not this module's concern — by the time a caller
reaches here, M7/M8 have already established that an LLM call is needed at
all; this only decides which one.
"""

import re
from typing import Literal

from app.core.config import settings

ModelTier = Literal["FAST", "STRONG"]

_COMPARISON_RE = re.compile(
    r"\b(bandingkan|dibandingkan|perbedaan|dibanding|perbandingan)\b", re.IGNORECASE
)
_QUESTION_WORD_RE = re.compile(
    r"\b(apa|bagaimana|siapa|mengapa|kapan|berapa|kenapa)\b", re.IGNORECASE
)


def choose_model_tier(query: str, distinct_document_count: int) -> ModelTier:
    # Multi-document synthesis (§34.3) — conflicting/complementary sources
    # need the stronger model to reconcile them.
    if distinct_document_count > 1:
        return "STRONG"

    # Comparison queries (§34.3).
    if _COMPARISON_RE.search(query):
        return "STRONG"

    # Multi-part query (§34.3) — more than one question-word suggests the
    # user asked several things at once (e.g. "apa dasar hukum, siapa
    # penyelenggara, dan bagaimana tahapannya?", §29.3's own example).
    if len(_QUESTION_WORD_RE.findall(query)) > 1:
        return "STRONG"

    return "FAST"


def select_model_for_tier(tier: ModelTier) -> tuple[str, str]:
    """Returns (model, fallback_model) for the given tier — the single
    place this mapping lives, shared by the M9 test endpoint and M10's
    AnswerGenerationService.
    """
    if tier == "STRONG":
        return settings.LLM_STRONG_MODEL, settings.LLM_STRONG_FALLBACK
    return settings.LLM_FAST_MODEL, settings.LLM_FAST_FALLBACK
