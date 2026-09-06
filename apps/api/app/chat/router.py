import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import Feedback, QueryLog
from app.auth.dependencies import require_role
from app.chat.chat_service import ChatService
from app.chat.models import Conversation, ConversationSummary, Message, MessageSource
from app.chat.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationPublic,
    ConversationRenameRequest,
    MessagePublic,
)
from app.chat.service import ConversationService
from app.core.database import get_db
from app.core.sse import sse_event
from app.knowledge.models import KnowledgeSpace
from app.llm.exceptions import LLMProviderUnavailable
from app.organizations.models import OrganizationMember, OrgRole
from app.retrieval.exceptions import RetrievalTimeout

router = APIRouter(tags=["chat"])

# Any org member can chat (§52: "VIEWER: chat dan read") — unlike the
# retrieval/reranking/llm test endpoints, which are gated to
# OWNER/ADMIN/EDITOR's "test knowledge" capability.
_CHAT_ROLES = (OrgRole.OWNER, OrgRole.ADMIN, OrgRole.EDITOR, OrgRole.VIEWER)


async def _validate_knowledge_space(
    db: AsyncSession, knowledge_space_id: uuid.UUID | None, organization_id: uuid.UUID
) -> None:
    if knowledge_space_id is None:
        return
    knowledge_space = (
        await db.execute(
            select(KnowledgeSpace).where(
                KnowledgeSpace.id == knowledge_space_id,
                KnowledgeSpace.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if knowledge_space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge space not found")


async def _get_or_create_conversation(
    db: AsyncSession,
    conversation_service: ConversationService,
    conversation_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Conversation:
    if conversation_id is None:
        return await conversation_service.create_conversation(organization_id, user_id)

    conversation = await conversation_service.get_conversation(
        conversation_id, organization_id, user_id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=list[ConversationPublic])
async def list_conversations(
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[Conversation]:
    service = ConversationService(db)
    return await service.list_conversations(membership.organization_id, membership.user_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    service = ConversationService(db)
    conversation = await service.get_conversation(
        conversation_id, membership.organization_id, membership.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    messages = await service.get_messages(conversation_id)
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessagePublic.model_validate(message, from_attributes=True) for message in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationPublic)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationRenameRequest,
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    service = ConversationService(db)
    conversation = await service.get_conversation(
        conversation_id, membership.organization_id, membership.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    conversation.title = body.title
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = ConversationService(db)
    conversation = await service.get_conversation(
        conversation_id, membership.organization_id, membership.user_id
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # No ORM relationship() is declared between these models (this
    # codebase's established pattern, see documents/router.py's own
    # delete_document) — explicit child-first ordering via bulk Core
    # deletes, since message_sources/feedback reference messages.id.
    message_ids_subquery = select(Message.id).where(Message.conversation_id == conversation.id)
    await db.execute(delete(MessageSource).where(MessageSource.message_id.in_(message_ids_subquery)))
    await db.execute(delete(Feedback).where(Feedback.message_id.in_(message_ids_subquery)))
    await db.execute(delete(Message).where(Message.conversation_id == conversation.id))
    await db.execute(
        delete(ConversationSummary).where(ConversationSummary.conversation_id == conversation.id)
    )
    # QueryLog is an analytics record (spec §62) that must survive the
    # conversation it was logged against — null the reference instead of
    # deleting the row, or overview/knowledge-gap history would be lost.
    await db.execute(
        update(QueryLog)
        .where(QueryLog.conversation_id == conversation.id)
        .values(conversation_id=None)
    )
    await db.delete(conversation)
    await db.commit()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    await _validate_knowledge_space(db, body.knowledge_space_id, membership.organization_id)

    conversation_service = ConversationService(db)
    conversation = await _get_or_create_conversation(
        db, conversation_service, body.conversation_id, membership.organization_id, membership.user_id
    )

    chat_service = ChatService(db)
    try:
        message_id, answer_response = await chat_service.answer(
            conversation, body.query, body.knowledge_space_id
        )
    except RetrievalTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Retrieval timed out"
        ) from exc
    except LLMProviderUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await db.commit()
    return ChatResponse(conversation_id=conversation.id, message_id=message_id, answer=answer_response)


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    membership: OrganizationMember = Depends(require_role(*_CHAT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _validate_knowledge_space(db, body.knowledge_space_id, membership.organization_id)

    conversation_service = ConversationService(db)
    conversation = await _get_or_create_conversation(
        db, conversation_service, body.conversation_id, membership.organization_id, membership.user_id
    )
    conversation_id = conversation.id

    chat_service = ChatService(db)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event_type, payload in chat_service.stream_answer(
                conversation, body.query, body.knowledge_space_id
            ):
                if event_type == "sources":
                    yield f"event: sources\ndata: {payload}\n\n"
                else:
                    yield sse_event(payload)
            await db.commit()
        except (RetrievalTimeout, LLMProviderUnavailable) as exc:
            yield f"event: error\ndata: {exc}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conversation_id)},
    )
