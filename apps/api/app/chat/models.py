"""Conversation orchestration models (M11 backend slice, spec §50-51).

`Chatbot`/`ChatbotKnowledgeSpace` exist only because §51's ERD ties
CONVERSATION to CHATBOT — no milestone target ever scopes chatbot
management, so one default Chatbot is auto-created per organization
(ConversationService), mirroring how registration already auto-creates a
default "General" KnowledgeSpace. There is no chatbot CRUD here.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessageRole(str, enum.Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class Chatbot(Base):
    __tablename__ = "chatbots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Assistant")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatbotKnowledgeSpace(Base):
    __tablename__ = "chatbot_knowledge_spaces"
    __table_args__ = (
        UniqueConstraint("chatbot_id", "knowledge_space_id", name="uq_chatbot_knowledge_space"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chatbot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chatbots.id"), nullable=False
    )
    knowledge_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_spaces.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    chatbot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chatbots.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    # Null until the first message sets it (e.g. from the first user query),
    # matching the ChatGPT-like UX (§65) of a title that appears after the
    # first turn, not chosen up front.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Gap audit 2026-09-15 (performance pass, incremental conversation
        # summarization): supersedes a plain conversation_id-only index —
        # ConversationService's recent-window (ORDER BY created_at DESC
        # LIMIT n) and incremental-summarization delta (created_at range
        # between two cursors) queries both need an efficient
        # (conversation_id, created_at) range scan, not just an equality
        # lookup on conversation_id.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Full §38 structured output for an ASSISTANT message (answer_type,
    # sections, insufficient_evidence, etc.) — null for USER messages.
    # `content` alone (the rendered summary) is what session-memory context
    # (§43) replays; this is for a future UI needing the raw structure.
    structured_answer: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MessageSource(Base):
    """Persists an ASSISTANT message's citations (spec §41) so the source
    drawer never has to recompute them later.
    """

    __tablename__ = "message_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False, index=True
    )
    source_label: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    structural_path_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # None for a DOCX-derived source — no stable page number exists there at
    # all (addendum §5); structural_path_text is the real citation location.
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConversationSummary(Base):
    """Rolling summary (spec §43) — one row per conversation, incrementally
    updated (never fully regenerated from the whole transcript) each time
    the recent-message window slides forward. See
    ConversationService.build_conversation_context.
    """

    __tablename__ = "conversation_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, unique=True
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Gap audit 2026-09-15 (performance pass): cursor marking "summary_text
    # already accounts for every message with created_at <= this value" —
    # lets build_conversation_context fold in only the messages that aged
    # out of the recent window since the last turn, instead of
    # re-summarizing the entire older-than-window transcript from scratch
    # every turn. NULL means nothing has been folded in yet.
    summarized_through_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
