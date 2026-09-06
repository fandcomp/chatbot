"""AnalyticsService (spec §90/§62-63) — writes QueryLog on every chat/test
query, maintains the KnowledgeGap aggregate whenever a query goes
unanswered, and computes the admin overview dashboard's numbers.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import (
    Feedback,
    FeedbackRating,
    KnowledgeGap,
    QueryLog,
    QueryLogSource,
)
from app.analytics.schemas import AnalyticsOverview
from app.core.config import settings
from app.core.text import normalize_query_text

_COST_PER_1K_TOKENS = {
    "FAST": settings.LLM_FAST_COST_PER_1K_TOKENS,
    "STRONG": settings.LLM_STRONG_COST_PER_1K_TOKENS,
}


def _estimate_cost(
    tier: str | None, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if tier is None or input_tokens is None or output_tokens is None:
        return None
    rate = _COST_PER_1K_TOKENS.get(tier)
    if rate is None:
        return None
    return ((input_tokens + output_tokens) / 1000) * rate


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log_query(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        source: QueryLogSource,
        query_text: str,
        retrieval_mode: str | None,
        reranked: bool,
        tier: str | None,
        insufficient_evidence: bool,
        retrieved_source_count: int,
        citation_count: int,
        retrieval_latency_ms: int | None,
        llm_latency_ms: int | None,
        total_latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        cache_hit: bool = False,
    ) -> None:
        self._db.add(
            QueryLog(
                organization_id=organization_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source=source,
                query_text=query_text,
                retrieval_mode=retrieval_mode,
                reranked=reranked,
                tier=tier,
                insufficient_evidence=insufficient_evidence,
                retrieved_source_count=retrieved_source_count,
                citation_count=citation_count,
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=llm_latency_ms,
                total_latency_ms=total_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=_estimate_cost(tier, input_tokens, output_tokens),
                cache_hit=cache_hit,
            )
        )
        if insufficient_evidence:
            await self._record_knowledge_gap(organization_id, query_text)
        await self._db.flush()

    async def _record_knowledge_gap(self, organization_id: uuid.UUID, query_text: str) -> None:
        normalized = normalize_query_text(query_text)
        now = datetime.now(UTC)
        existing = (
            await self._db.execute(
                select(KnowledgeGap).where(
                    KnowledgeGap.organization_id == organization_id,
                    KnowledgeGap.normalized_query == normalized,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.frequency += 1
            existing.last_asked_at = now
        else:
            self._db.add(
                KnowledgeGap(
                    organization_id=organization_id,
                    normalized_query=normalized,
                    sample_query_text=query_text,
                    frequency=1,
                    last_asked_at=now,
                )
            )

    async def list_knowledge_gaps(
        self, organization_id: uuid.UUID, limit: int = 20
    ) -> list[KnowledgeGap]:
        result = await self._db.execute(
            select(KnowledgeGap)
            .where(KnowledgeGap.organization_id == organization_id)
            .order_by(KnowledgeGap.frequency.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_overview(self, organization_id: uuid.UUID) -> AnalyticsOverview:
        # Test Knowledge traffic (admin previews) is deliberately excluded —
        # this dashboard reflects real end-user chat quality, not admin QA.
        totals = (
            await self._db.execute(
                select(
                    func.count(QueryLog.id),
                    func.sum(case((QueryLog.insufficient_evidence.is_(False), 1), else_=0)),
                    func.sum(case((QueryLog.insufficient_evidence.is_(True), 1), else_=0)),
                    func.avg(QueryLog.total_latency_ms),
                    func.percentile_cont(0.95).within_group(QueryLog.total_latency_ms),
                    func.avg(QueryLog.estimated_cost_usd),
                    func.sum(case((QueryLog.citation_count > 0, 1), else_=0)),
                    func.sum(case((QueryLog.retrieved_source_count > 0, 1), else_=0)),
                    func.sum(case((QueryLog.cache_hit.is_(True), 1), else_=0)),
                ).where(
                    QueryLog.organization_id == organization_id,
                    QueryLog.source == QueryLogSource.CHAT,
                )
            )
        ).one()
        (
            total_questions,
            answered,
            insufficient_evidence,
            avg_latency_ms,
            p95_latency_ms,
            avg_cost_usd,
            citation_hits,
            retrieval_hits,
            cache_hits,
        ) = totals

        feedback_rows = (
            await self._db.execute(
                select(Feedback.rating, func.count(Feedback.id))
                .where(Feedback.organization_id == organization_id)
                .group_by(Feedback.rating)
            )
        ).all()
        feedback_by_rating: dict[FeedbackRating, int] = {row[0]: row[1] for row in feedback_rows}

        total_questions = total_questions or 0
        return AnalyticsOverview(
            total_questions=total_questions,
            answered=answered or 0,
            insufficient_evidence=insufficient_evidence or 0,
            avg_latency_ms=float(avg_latency_ms) if avg_latency_ms is not None else None,
            p95_latency_ms=float(p95_latency_ms) if p95_latency_ms is not None else None,
            avg_cost_usd=float(avg_cost_usd) if avg_cost_usd is not None else None,
            citation_coverage=(citation_hits or 0) / total_questions if total_questions else 0.0,
            retrieval_success=(retrieval_hits or 0) / total_questions if total_questions else 0.0,
            cache_hit_rate=(cache_hits or 0) / total_questions if total_questions else 0.0,
            thumbs_up=feedback_by_rating.get(FeedbackRating.THUMBS_UP, 0),
            thumbs_down=feedback_by_rating.get(FeedbackRating.THUMBS_DOWN, 0),
        )
