"""Structured LLM Output (spec §38) — the LLM never produces UI directly,
only this validated shape. Frontend renders it (M11).
"""

import enum

from pydantic import BaseModel


class QueryIntent(str, enum.Enum):
    """spec §30 — minimal vocabulary."""

    FACTUAL_LOOKUP = "FACTUAL_LOOKUP"
    PROCEDURAL_EXPLANATION = "PROCEDURAL_EXPLANATION"
    LEGAL_BASIS_VALIDATION = "LEGAL_BASIS_VALIDATION"
    DEFINITION = "DEFINITION"
    REQUIREMENT = "REQUIREMENT"
    PROHIBITION = "PROHIBITION"
    AUTHORITY = "AUTHORITY"
    DEADLINE = "DEADLINE"
    COMPARISON = "COMPARISON"
    DOCUMENT_LOOKUP = "DOCUMENT_LOOKUP"
    OTHER = "OTHER"


class Claim(BaseModel):
    text: str
    # S1/S2/... labels the LLM was given in the Evidence Pack — never a
    # number the LLM invented itself (spec §41).
    source_ids: list[str]


class StructuredAnswer(BaseModel):
    answer_type: QueryIntent
    summary: str
    sections: list[str]
    claims: list[Claim]
    insufficient_evidence: bool
    reason_if_insufficient: str | None
