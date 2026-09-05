"""Claim verification results (spec §40, addendum §34) and the final
verified-answer response shape M10's endpoint returns.
"""

import enum
import uuid

from pydantic import BaseModel

from app.citations.schemas import Citation
from app.llm.answer_schemas import QueryIntent
from app.llm.model_router import ModelTier
from app.retrieval.schemas import RetrievalMode


class ClaimStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNCERTAIN = "UNCERTAIN"


class VerifiedClaim(BaseModel):
    text: str
    source_ids: list[str]
    status: ClaimStatus
    # Populated only for a structural failure (unknown source id, or
    # addendum §34's terminology mismatch) — never a free-form explanation
    # of a lexical-overlap result.
    invalid_reason: str | None


class AnswerRequest(BaseModel):
    query: str
    knowledge_space_id: uuid.UUID | None = None


class AnswerResponse(BaseModel):
    query: str
    tier: ModelTier
    retrieval_mode: RetrievalMode
    reranked: bool
    insufficient_evidence: bool
    reason_if_insufficient: str | None
    answer_type: QueryIntent
    summary: str
    sections: list[str]
    claims: list[VerifiedClaim]
    citations: dict[str, Citation]
