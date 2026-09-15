"""ConversationService (spec §90) — conversation/message persistence and
session memory (§43: rolling summary + recent messages), independent of
the answer-generation pipeline itself (see app/chat/chat_service.py).

Conversations are scoped to (organization_id, user_id) — each user sees
only their own chat history (§67's sidebar is a per-user concept, matching
the ChatGPT-like UX §65 asks for), never other org members' conversations,
even though they share the same tenant.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import (
    Chatbot,
    ChatbotKnowledgeSpace,
    Conversation,
    ConversationSummary,
    Message,
    MessageRole,
    MessageSource,
)
from app.knowledge.models import KnowledgeSpace
from app.llm.gateway import LLMGateway
from app.llm.model_router import select_model_for_tier


class ConversationService:
    def __init__(self, db: AsyncSession, llm_gateway: LLMGateway | None = None) -> None:
        self._db = db
        self._llm_gateway = llm_gateway or LLMGateway()

    async def get_or_create_default_chatbot(self, organization_id: uuid.UUID) -> Chatbot:
        chatbot = (
            await self._db.execute(
                select(Chatbot).where(Chatbot.organization_id == organization_id)
            )
        ).scalar_one_or_none()
        if chatbot is not None:
            return chatbot

        chatbot = Chatbot(organization_id=organization_id, name="Assistant")
        self._db.add(chatbot)
        await self._db.flush()

        knowledge_spaces = (
            await self._db.execute(
                select(KnowledgeSpace).where(KnowledgeSpace.organization_id == organization_id)
            )
        ).scalars().all()
        for knowledge_space in knowledge_spaces:
            self._db.add(
                ChatbotKnowledgeSpace(chatbot_id=chatbot.id, knowledge_space_id=knowledge_space.id)
            )
        await self._db.flush()
        return chatbot

    async def create_conversation(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation:
        chatbot = await self.get_or_create_default_chatbot(organization_id)
        conversation = Conversation(
            organization_id=organization_id, chatbot_id=chatbot.id, user_id=user_id
        )
        self._db.add(conversation)
        await self._db.flush()
        return conversation

    async def list_conversations(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Conversation]:
        result = await self._db.execute(
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.user_id == user_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_conversation(
        self, conversation_id: uuid.UUID, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        return (
            await self._db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.organization_id == organization_id,
                    Conversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get_messages(self, conversation_id: uuid.UUID) -> list[Message]:
        result = await self._db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())

    async def append_message(
        self,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        structured_answer: dict | None = None,
        sources: list[dict] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            structured_answer=structured_answer,
        )
        self._db.add(message)
        await self._db.flush()

        for source in sources or []:
            self._db.add(MessageSource(message_id=message.id, **source))
        await self._db.flush()
        return message

    async def set_title_if_unset(self, conversation: Conversation, first_query: str) -> None:
        if conversation.title is None:
            conversation.title = first_query[:255]

    async def _recent_messages(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        """The last `limit` messages, chronological (oldest of the window
        first). `limit <= 0` preserves build_conversation_context's original
        "no window, everything is recent" contract — unbounded, but no
        caller passes a non-positive limit today.
        """
        if limit <= 0:
            return await self.get_messages(conversation_id)
        result = await self._db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def _messages_between(
        self, conversation_id: uuid.UUID, after: datetime | None, before: datetime
    ) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.created_at < before)
            .order_by(Message.created_at.asc())
        )
        if after is not None:
            stmt = stmt.where(Message.created_at > after)
        return list((await self._db.execute(stmt)).scalars().all())

    async def _get_summary(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        return (
            await self._db.execute(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation_id
                )
            )
        ).scalar_one_or_none()

    async def build_conversation_context(
        self, conversation_id: uuid.UUID, recent_limit: int
    ) -> str | None:
        """Renders §43's "Conversation Summary / Recent messages" block, or
        None for a brand-new conversation with nothing to replay yet.

        Unlike a naive "fetch everything, resummarize everything older than
        the window" approach, this only ever fetches the bounded recent
        window plus the small delta of messages that aged out of it since
        the summary was last updated, and folds just that delta into the
        existing summary — see ConversationSummary.summarized_through_created_at
        and _summarize_incremental.

        (Assumes recent_limit is effectively constant for a conversation's
        lifetime: changing it mid-conversation can't corrupt the summary,
        but may transiently let a message appear in both the summary and the
        recent window until it ages out again.)
        """
        recent = await self._recent_messages(conversation_id, recent_limit)
        if not recent:
            return None

        summary_row = await self._get_summary(conversation_id)
        summary_text = summary_row.summary_text if summary_row is not None else None
        already_summarized_through = (
            summary_row.summarized_through_created_at if summary_row is not None else None
        )

        new_older_messages = await self._messages_between(
            conversation_id, after=already_summarized_through, before=recent[0].created_at
        )
        if new_older_messages:
            summary_text = await self._summarize_incremental(summary_text, new_older_messages)
            await self._save_summary(
                conversation_id, summary_text, new_older_messages[-1].created_at
            )

        lines = []
        if summary_text:
            lines.append(f"Conversation Summary:\n{summary_text}")
        recent_text = "\n".join(
            f"{msg.role.value.title()}: {msg.content}" for msg in recent
        )
        lines.append(f"Recent messages:\n{recent_text}")
        return "\n\n".join(lines)

    async def _summarize_incremental(
        self, existing_summary: str | None, new_messages: list[Message]
    ) -> str:
        transcript = "\n".join(f"{msg.role.value.title()}: {msg.content}" for msg in new_messages)
        model, fallback_model = select_model_for_tier("FAST")
        if existing_summary is None:
            system_content = (
                "Summarize this conversation transcript in 2-4 sentences, "
                "focusing on the main topic and what has already been "
                "discussed. Do not answer any question in it, only summarize."
            )
            user_content = transcript
        else:
            system_content = (
                "You maintain a running summary of an ongoing conversation. "
                "Given the current summary and the new messages that followed "
                "it, write one updated 2-4 sentence summary covering both the "
                "prior summary's content and the new messages. Do not answer "
                "any question in it, only summarize."
            )
            user_content = f"Current summary:\n{existing_summary}\n\nNew messages:\n{transcript}"
        return await self._llm_gateway.generate(
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            model=model,
            fallback_model=fallback_model,
        )

    async def _save_summary(
        self,
        conversation_id: uuid.UUID,
        summary_text: str,
        summarized_through_created_at: datetime,
    ) -> None:
        existing = await self._get_summary(conversation_id)
        if existing is not None:
            existing.summary_text = summary_text
            existing.summarized_through_created_at = summarized_through_created_at
        else:
            self._db.add(
                ConversationSummary(
                    conversation_id=conversation_id,
                    summary_text=summary_text,
                    summarized_through_created_at=summarized_through_created_at,
                )
            )
        await self._db.flush()
