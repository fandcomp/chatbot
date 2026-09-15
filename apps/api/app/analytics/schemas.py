import uuid
from datetime import datetime

from pydantic import BaseModel

from app.analytics.models import FeedbackRating
from app.documents.models import DocumentLifecycleStatus


class KnowledgeGapPublic(BaseModel):
    query: str
    frequency: int
    last_asked_at: datetime


class TopQuestionPublic(BaseModel):
    query: str
    frequency: int
    last_asked_at: datetime


class DocumentMentionPublic(BaseModel):
    document_id: uuid.UUID
    document_title: str
    citation_count: int


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


class DocumentStatusCount(BaseModel):
    status: DocumentLifecycleStatus
    count: int


class KnowledgeBaseOverview(BaseModel):
    # spec §82's illustrative "Admin Overview" — total documents, total
    # currently-indexed chunks (only those belonging to each document's
    # ACTIVE version, not stale SUPERSEDED/ARCHIVED/FAILED leftovers), and
    # a status breakdown covering every DocumentLifecycleStatus actually
    # present (not forced into the example's 3 illustrative buckets —
    # nothing in the spec maps the other 7 statuses to "Ready"/"Review
    # Required"/"Failed", so showing the real statuses is more correct
    # than fabricating an unspecified mapping).
    total_documents: int
    total_indexed_chunks: int
    status_breakdown: list[DocumentStatusCount]


class FeedbackRequest(BaseModel):
    rating: FeedbackRating
    comment: str | None = None


class FeedbackPublic(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rating: FeedbackRating
    comment: str | None
