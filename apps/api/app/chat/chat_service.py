"""ChatService (spec §90) — orchestrates a full conversational turn:
session memory (ConversationService) -> Retrieval (M7) -> Reranking (M8) ->
Context Builder + LLM (M9/M10) -> Claim Verification -> Citation mapping,
then persists both turns via ConversationService.

Non-streaming (answer) and streaming (stream_answer) converge on the same
ClaimVerificationService/AdaptiveCitationService — the streaming path just
gets its Claim list from app/chat/inline_citation_parser.py instead of
generate_structured's JSON array (see app/llm/context_builder.py's module
docstring for why streaming can't use generate_structured directly).

`answer()` also checks AnswerCacheService on a conversation's first,
org-wide (not knowledge-space-scoped) turn — see that module's docstring
for the caching scope decisions (spec §45/§47 rule 9). `stream_answer()`
deliberately does not: caching a token stream would mean replaying a
stored string as if it were freshly generated, which adds meaningful
complexity for a path that is already fast due to TTFT streaming.
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import QueryLogSource
from app.analytics.service import AnalyticsService
from app.caching.answer_cache import AnswerCacheService
from app.chat.inline_citation_parser import parse_inline_citations
from app.chat.models import Conversation, MessageRole
from app.chat.service import ConversationService
from app.citations.service import AdaptiveCitationService
from app.core.config import settings
from app.llm.answer_schemas import QueryIntent
from app.llm.answer_service import AnswerGenerationService
from app.llm.context_builder import build_streaming_messages
from app.llm.gateway import LLMGateway
from app.llm.model_router import choose_model_tier, select_model_for_tier
from app.reranking.schemas import Evidence
from app.reranking.service import RerankingService
from app.retrieval.exceptions import RetrievalTimeout
from app.retrieval.service import RetrievalService
from app.verification.schemas import AnswerResponse
from app.verification.service import ClaimVerificationService

_INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Informasi tersebut belum ditemukan pada dokumen yang tersedia dalam "
    "basis pengetahuan saat ini."
)


def _evidence_to_sources(evidence: list[Evidence]) -> list[dict]:
    return [
        {
            "source_label": item.evidence_id,
            "chunk_id": item.chunk_id,
            "document_id": item.document_id,
            "structural_path_text": item.structural_path_text,
            "page_start": item.page_start,
            "page_end": item.page_end,
        }
        for item in evidence
    ]


class ChatService:
    def __init__(self, db: AsyncSession, llm_gateway: LLMGateway | None = None) -> None:
        self._db = db
        self._llm_gateway = llm_gateway or LLMGateway()
        self._conversations = ConversationService(db, self._llm_gateway)
        self._retrieval = RetrievalService(db)
        self._reranking = RerankingService(db)
        self._citations = AdaptiveCitationService(db)
        self._verification = ClaimVerificationService()
        self._analytics = AnalyticsService(db)
        self._answer_cache = AnswerCacheService()

    async def _gather_evidence(
        self, organization_id: uuid.UUID, query: str, knowledge_space_id: uuid.UUID | None
    ):
        try:
            retrieval_response = await asyncio.wait_for(
                self._retrieval.retrieve(
                    organization_id=organization_id,
                    query=query,
                    knowledge_space_id=knowledge_space_id,
                ),
                timeout=settings.RETRIEVAL_TIMEOUT,
            )
        except TimeoutError as exc:
            raise RetrievalTimeout("Retrieval timed out") from exc
        return await self._reranking.select_evidence(retrieval_response)

    async def answer(
        self,
        conversation: Conversation,
        query: str,
        knowledge_space_id: uuid.UUID | None,
    ) -> tuple[uuid.UUID, AnswerResponse]:
        turn_started = time.perf_counter()
        await self._conversations.set_title_if_unset(conversation, query)
        conversation_context = await self._conversations.build_conversation_context(
            conversation.id, settings.MAX_RECENT_MESSAGES
        )
        await self._conversations.append_message(conversation.id, MessageRole.USER, query)

        # Answer cache (spec §45/§47 rule 9) only applies to a conversation's
        # first turn — see AnswerCacheService's own docstring for why a
        # context-free cache key can't safely serve a follow-up question.
        if conversation_context is None and knowledge_space_id is None:
            cached = await self._answer_cache.get(
                conversation.organization_id, conversation.chatbot_id, query
            )
            if cached is not None:
                cached_answer, cached_sources = cached
                message = await self._conversations.append_message(
                    conversation.id,
                    MessageRole.ASSISTANT,
                    cached_answer.summary,
                    structured_answer=cached_answer.model_dump(mode="json"),
                    sources=cached_sources,
                )
                await self._analytics.log_query(
                    organization_id=conversation.organization_id,
                    user_id=conversation.user_id,
                    conversation_id=conversation.id,
                    source=QueryLogSource.CHAT,
                    query_text=query,
                    retrieval_mode=cached_answer.retrieval_mode,
                    reranked=cached_answer.reranked,
                    tier=cached_answer.tier,
                    insufficient_evidence=False,
                    retrieved_source_count=len(cached_sources),
                    citation_count=len(cached_answer.citations),
                    retrieval_latency_ms=0,
                    llm_latency_ms=0,
                    total_latency_ms=int((time.perf_counter() - turn_started) * 1000),
                    input_tokens=None,
                    output_tokens=None,
                    cache_hit=True,
                )
                return message.id, cached_answer

        retrieval_started = time.perf_counter()
        evidence_response = await self._gather_evidence(
            conversation.organization_id, query, knowledge_space_id
        )
        retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)

        if not evidence_response.evidence:
            answer_response = AnswerResponse(
                query=query,
                tier="FAST",
                retrieval_mode=evidence_response.retrieval_mode,
                reranked=evidence_response.reranked,
                insufficient_evidence=True,
                reason_if_insufficient=_INSUFFICIENT_EVIDENCE_MESSAGE,
                answer_type=QueryIntent.OTHER,
                summary=_INSUFFICIENT_EVIDENCE_MESSAGE,
                sections=[],
                claims=[],
                citations={},
            )
            message = await self._conversations.append_message(
                conversation.id, MessageRole.ASSISTANT, answer_response.summary
            )
            await self._analytics.log_query(
                organization_id=conversation.organization_id,
                user_id=conversation.user_id,
                conversation_id=conversation.id,
                source=QueryLogSource.CHAT,
                query_text=query,
                retrieval_mode=evidence_response.retrieval_mode,
                reranked=evidence_response.reranked,
                tier=None,
                insufficient_evidence=True,
                retrieved_source_count=0,
                citation_count=0,
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=None,
                total_latency_ms=int((time.perf_counter() - turn_started) * 1000),
                input_tokens=None,
                output_tokens=None,
            )
            return message.id, answer_response

        distinct_document_count = len(
            {item.document_id for item in evidence_response.evidence}
        )
        tier = choose_model_tier(query, distinct_document_count)

        llm_started = time.perf_counter()
        structured_answer, usage = await AnswerGenerationService(
            self._llm_gateway
        ).generate_answer(query, evidence_response.evidence, tier, conversation_context)
        llm_latency_ms = int((time.perf_counter() - llm_started) * 1000)

        verified_claims = self._verification.verify(
            structured_answer.claims, evidence_response.evidence
        )
        citations = await self._citations.build_citations(
            evidence_response.evidence, conversation.organization_id
        )

        answer_response = AnswerResponse(
            query=query,
            tier=tier,
            retrieval_mode=evidence_response.retrieval_mode,
            reranked=evidence_response.reranked,
            insufficient_evidence=structured_answer.insufficient_evidence,
            reason_if_insufficient=structured_answer.reason_if_insufficient,
            answer_type=structured_answer.answer_type,
            summary=structured_answer.summary,
            sections=structured_answer.sections,
            claims=verified_claims,
            citations=citations,
        )
        message = await self._conversations.append_message(
            conversation.id,
            MessageRole.ASSISTANT,
            structured_answer.summary,
            structured_answer=structured_answer.model_dump(mode="json"),
            sources=_evidence_to_sources(evidence_response.evidence),
        )
        await self._analytics.log_query(
            organization_id=conversation.organization_id,
            user_id=conversation.user_id,
            conversation_id=conversation.id,
            source=QueryLogSource.CHAT,
            query_text=query,
            retrieval_mode=evidence_response.retrieval_mode,
            reranked=evidence_response.reranked,
            tier=tier,
            insufficient_evidence=structured_answer.insufficient_evidence,
            retrieved_source_count=len(evidence_response.evidence),
            citation_count=len(citations),
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            total_latency_ms=int((time.perf_counter() - turn_started) * 1000),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        if (
            conversation_context is None
            and knowledge_space_id is None
            and not structured_answer.insufficient_evidence
        ):
            await self._answer_cache.set(
                conversation.organization_id,
                conversation.chatbot_id,
                query,
                answer_response,
                _evidence_to_sources(evidence_response.evidence),
            )
        return message.id, answer_response

    async def stream_answer(
        self,
        conversation: Conversation,
        query: str,
        knowledge_space_id: uuid.UUID | None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Yields ("token", text) deltas, then a single ("sources", json)
        event once generation completes.
        """
        turn_started = time.perf_counter()
        await self._conversations.set_title_if_unset(conversation, query)
        conversation_context = await self._conversations.build_conversation_context(
            conversation.id, settings.MAX_RECENT_MESSAGES
        )
        await self._conversations.append_message(conversation.id, MessageRole.USER, query)

        retrieval_started = time.perf_counter()
        evidence_response = await self._gather_evidence(
            conversation.organization_id, query, knowledge_space_id
        )
        retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)

        if not evidence_response.evidence:
            yield "token", _INSUFFICIENT_EVIDENCE_MESSAGE
            await self._conversations.append_message(
                conversation.id, MessageRole.ASSISTANT, _INSUFFICIENT_EVIDENCE_MESSAGE
            )
            yield "sources", json.dumps(
                {"insufficient_evidence": True, "claims": [], "citations": {}}
            )
            await self._analytics.log_query(
                organization_id=conversation.organization_id,
                user_id=conversation.user_id,
                conversation_id=conversation.id,
                source=QueryLogSource.CHAT,
                query_text=query,
                retrieval_mode=evidence_response.retrieval_mode,
                reranked=evidence_response.reranked,
                tier=None,
                insufficient_evidence=True,
                retrieved_source_count=0,
                citation_count=0,
                retrieval_latency_ms=retrieval_latency_ms,
                llm_latency_ms=None,
                total_latency_ms=int((time.perf_counter() - turn_started) * 1000),
                input_tokens=None,
                output_tokens=None,
            )
            return

        distinct_document_count = len(
            {item.document_id for item in evidence_response.evidence}
        )
        tier = choose_model_tier(query, distinct_document_count)
        model, _fallback_model = select_model_for_tier(tier)
        messages = build_streaming_messages(query, evidence_response.evidence, conversation_context)

        llm_started = time.perf_counter()
        full_text = ""
        async for token in self._llm_gateway.stream(messages=messages, model=model):
            full_text += token
            yield "token", token
        llm_latency_ms = int((time.perf_counter() - llm_started) * 1000)

        claims = parse_inline_citations(full_text)
        verified_claims = self._verification.verify(claims, evidence_response.evidence)
        citations = await self._citations.build_citations(
            evidence_response.evidence, conversation.organization_id
        )

        await self._conversations.append_message(
            conversation.id,
            MessageRole.ASSISTANT,
            full_text,
            sources=_evidence_to_sources(evidence_response.evidence),
        )

        yield "sources", json.dumps(
            {
                "insufficient_evidence": False,
                "claims": [claim.model_dump(mode="json") for claim in verified_claims],
                "citations": {
                    source_id: citation.model_dump(mode="json")
                    for source_id, citation in citations.items()
                },
            }
        )

        # No token usage for the streaming path (see gateway.py's TokenUsage
        # docstring) — input_tokens/output_tokens/estimated_cost log as null.
        await self._analytics.log_query(
            organization_id=conversation.organization_id,
            user_id=conversation.user_id,
            conversation_id=conversation.id,
            source=QueryLogSource.CHAT,
            query_text=query,
            retrieval_mode=evidence_response.retrieval_mode,
            reranked=evidence_response.reranked,
            tier=tier,
            insufficient_evidence=False,
            retrieved_source_count=len(evidence_response.evidence),
            citation_count=len(citations),
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            total_latency_ms=int((time.perf_counter() - turn_started) * 1000),
            input_tokens=None,
            output_tokens=None,
        )
