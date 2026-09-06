"""Query logs, knowledge gaps, and feedback (spec §62-63, §92). QueryLog is
written by both ChatService (real chat) and TestKnowledgeService (admin
preview) — `source` distinguishes them so overview metrics can include or
exclude test traffic.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QueryLogSource(str, enum.Enum):
    CHAT = "CHAT"
    TEST_KNOWLEDGE = "TEST_KNOWLEDGE"


class FeedbackRating(str, enum.Enum):
    THUMBS_UP = "THUMBS_UP"
    THUMBS_DOWN = "THUMBS_DOWN"


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True
    )
    source: Mapped[QueryLogSource] = mapped_column(
        SAEnum(QueryLogSource, name="query_log_source"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reranked: Mapped[bool] = mapped_column(nullable=False, default=False)
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    insufficient_evidence: Mapped[bool] = mapped_column(nullable=False, default=False)
    retrieved_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Coarse breakdown only (spec §92 lists finer-grained stages than this
    # codebase's ChatService boundaries cleanly expose without invasive
    # pipeline instrumentation) — retrieval_latency_ms covers embedding +
    # dense/sparse search + reranking combined.
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # Null for the streaming chat path — HF only reports usage there if
    # stream_options.include_usage is requested, which this codebase's
    # LLMGateway.stream() does not do (see gateway.py's TokenUsage docstring).
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KnowledgeGap(Base):
    """spec §62 — aggregated by normalized query text, incremented every
    time a QueryLog has insufficient_evidence=true.
    """

    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_query", name="uq_knowledge_gap"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False)
    sample_query_text: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Feedback(Base):
    """spec §75-76 — thumbs up/down on an assistant Message."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        SAEnum(FeedbackRating, name="feedback_rating"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
