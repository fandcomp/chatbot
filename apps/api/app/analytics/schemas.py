import uuid
from datetime import datetime

from pydantic import BaseModel

from app.analytics.models import FeedbackRating


class KnowledgeGapPublic(BaseModel):
    query: str
    frequency: int
    last_asked_at: datetime


class AnalyticsOverview(BaseModel):
    total_questions: int
    answered: int
    insufficient_evidence: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    avg_cost_usd: float | None
    # Fractions in [0, 1] — spec §63's "citation coverage" / "retrieval
    # success", not raw counts.
    citation_coverage: float
    retrieval_success: float
    # Fraction of CHAT turns served from the answer cache (spec §45/§47 rule
    # 9) instead of running retrieval+LLM — see app/caching/answer_cache.py.
    cache_hit_rate: float
    thumbs_up: int
    thumbs_down: int


class FeedbackRequest(BaseModel):
    rating: FeedbackRating
    comment: str | None = None


class FeedbackPublic(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None
