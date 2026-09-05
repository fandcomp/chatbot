"""ChatService (spec §90) — orchestrates a full conversational turn:
session memory (ConversationService) -> Retrieval (M7) -> Reranking (M8) ->
Context Builder + LLM (M9/M10) -> Claim Verification -> Citation mapping,
then persists both turns via ConversationService.

Non-streaming (answer) and streaming (stream_answer) converge on the same
ClaimVerificationService/AdaptiveCitationService — the streaming path just
gets its Claim list from app/chat/inline_citation_parser.py instead of
generate_structured's JSON array (see app/llm/context_builder.py's module
docstring for why streaming can't use generate_structured directly).
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

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
        await self._conversations.set_title_if_unset(conversation, query)
        conversation_context = await self._conversations.build_conversation_context(
            conversation.id, settings.MAX_RECENT_MESSAGES
        )
        await self._conversations.append_message(conversation.id, MessageRole.USER, query)

        evidence_response = await self._gather_evidence(
            conversation.organization_id, query, knowledge_space_id
        )

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
            return message.id, answer_response

        distinct_document_count = len(
            {item.document_id for item in evidence_response.evidence}
        )
        tier = choose_model_tier(query, distinct_document_count)

        structured_answer = await AnswerGenerationService(self._llm_gateway).generate_answer(
            query, evidence_response.evidence, tier, conversation_context
        )
        verified_claims = self._verification.verify(
            structured_answer.claims, evidence_response.evidence
        )
        citations = await self._citations.build_citations(evidence_response.evidence)

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
        await self._conversations.set_title_if_unset(conversation, query)
        conversation_context = await self._conversations.build_conversation_context(
            conversation.id, settings.MAX_RECENT_MESSAGES
        )
        await self._conversations.append_message(conversation.id, MessageRole.USER, query)

        evidence_response = await self._gather_evidence(
            conversation.organization_id, query, knowledge_space_id
        )

        if not evidence_response.evidence:
            yield "token", _INSUFFICIENT_EVIDENCE_MESSAGE
            await self._conversations.append_message(
                conversation.id, MessageRole.ASSISTANT, _INSUFFICIENT_EVIDENCE_MESSAGE
            )
            yield "sources", json.dumps(
                {"insufficient_evidence": True, "claims": [], "citations": {}}
            )
            return

        distinct_document_count = len(
            {item.document_id for item in evidence_response.evidence}
        )
        tier = choose_model_tier(query, distinct_document_count)
        model, _fallback_model = select_model_for_tier(tier)
        messages = build_streaming_messages(query, evidence_response.evidence, conversation_context)

        full_text = ""
        async for token in self._llm_gateway.stream(messages=messages, model=model):
            full_text += token
            yield "token", token

        claims = parse_inline_citations(full_text)
        verified_claims = self._verification.verify(claims, evidence_response.evidence)
        citations = await self._citations.build_citations(evidence_response.evidence)

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
