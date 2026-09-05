import uuid
from datetime import datetime

from pydantic import BaseModel

from app.chat.models import MessageRole
from app.verification.schemas import AnswerResponse


class ChatRequest(BaseModel):
    query: str
    # Omit to start a new conversation (spec §66's "New Chat").
    conversation_id: uuid.UUID | None = None
    knowledge_space_id: uuid.UUID | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: AnswerResponse


class ConversationPublic(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessagePublic(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class ConversationDetail(ConversationPublic):
    messages: list[MessagePublic]


class ConversationRenameRequest(BaseModel):
    title: str
