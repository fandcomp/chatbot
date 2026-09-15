"""Regression tests for ConversationService's incremental conversation
summarization (gap audit 2026-09-15, performance pass finding #5) —
build_conversation_context must only ever send the small delta of
newly-aged-out messages to the summarization LLM call, never the whole
older-than-window transcript from scratch on every turn.

Exercises ConversationService directly (not through /chat) so each turn's
LLM call can be asserted precisely without also mocking retrieval/answer
generation.

Requires `docker compose up -d` to be running from the repo root.
"""

import uuid
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.chat.models import ConversationSummary, MessageRole
from app.chat.service import ConversationService
from app.core.database import async_session_factory
from app.organizations.models import OrganizationMember

REGISTER_PAYLOAD = {
    "organization_name": "Summarization Test Org",
    "email": "owner@summarization-test.io",
    "password": "supersecret123",
}


async def _register_and_get_ids(client_factory) -> tuple[uuid.UUID, uuid.UUID]:
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    async with async_session_factory() as db:
        member = (await db.execute(select(OrganizationMember))).scalars().first()
        return member.organization_id, member.user_id


async def _append_turn(
    service: ConversationService, db, conversation_id: uuid.UUID, index: int
) -> None:
    """Appends one USER+ASSISTANT turn, committing after each message —
    Postgres' `now()` is transaction-start time, so messages inserted
    without an intervening commit would all get an identical created_at,
    breaking the created_at-ordered cursor this design relies on. A real
    turn always has genuine wall-clock time (retrieval + generation)
    between the two appends, so this only matters for test setup.
    """
    await service.append_message(conversation_id, MessageRole.USER, f"q{index}")
    await db.commit()
    await service.append_message(conversation_id, MessageRole.ASSISTANT, f"a{index}")
    await db.commit()


async def test_build_conversation_context_returns_none_for_a_brand_new_conversation(
    client_factory,
) -> None:
    organization_id, user_id = await _register_and_get_ids(client_factory)
    async with async_session_factory() as db:
        service = ConversationService(db, llm_gateway=AsyncMock())
        conversation = await service.create_conversation(organization_id, user_id)
        await db.commit()

        context = await service.build_conversation_context(conversation.id, recent_limit=4)

    assert context is None


async def test_no_summarization_call_while_every_message_fits_the_recent_window(
    client_factory,
) -> None:
    organization_id, user_id = await _register_and_get_ids(client_factory)
    mock_llm = AsyncMock()
    async with async_session_factory() as db:
        service = ConversationService(db, llm_gateway=mock_llm)
        conversation = await service.create_conversation(organization_id, user_id)
        for i in range(4):
            await _append_turn(service, db, conversation.id, i)

        context = await service.build_conversation_context(conversation.id, recent_limit=8)

    assert context is not None
    assert "Conversation Summary" not in context
    mock_llm.generate.assert_not_called()


async def test_first_summarization_only_covers_messages_outside_the_recent_window(
    client_factory,
) -> None:
    organization_id, user_id = await _register_and_get_ids(client_factory)
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Ringkasan awal.")
    async with async_session_factory() as db:
        service = ConversationService(db, llm_gateway=mock_llm)
        conversation = await service.create_conversation(organization_id, user_id)
        # 6 messages total; recent_limit=4 keeps [q1,a1,q2,a2] as "recent",
        # leaving only [q0,a0] to fold into the summary.
        for i in range(3):
            await _append_turn(service, db, conversation.id, i)

        context = await service.build_conversation_context(conversation.id, recent_limit=4)
        await db.commit()

    assert mock_llm.generate.call_count == 1
    transcript = mock_llm.generate.call_args.kwargs["messages"][1]["content"]
    assert "q0" in transcript
    assert "a0" in transcript
    assert "q2" not in transcript  # still inside the recent window
    assert "Conversation Summary" in context
    assert "Ringkasan awal." in context

    async with async_session_factory() as db:
        summary_row = (
            await db.execute(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation.id
                )
            )
        ).scalar_one()
        assert summary_row.summarized_through_created_at is not None


async def test_later_turn_sends_only_the_new_delta_not_the_whole_older_history(
    client_factory,
) -> None:
    """The regression this fix targets: a naive "resummarize everything
    older than the window" approach would resend q0/a0 here too, with the
    transcript sent growing without bound as the conversation lengthens.
    """
    organization_id, user_id = await _register_and_get_ids(client_factory)
    mock_llm = AsyncMock()
    async with async_session_factory() as db:
        service = ConversationService(db, llm_gateway=mock_llm)
        conversation = await service.create_conversation(organization_id, user_id)
        for i in range(3):
            await _append_turn(service, db, conversation.id, i)

        mock_llm.generate = AsyncMock(return_value="Ringkasan turn 1.")
        await service.build_conversation_context(conversation.id, recent_limit=4)
        await db.commit()

        # One more turn's worth of messages ages q1/a1 out of the window.
        await _append_turn(service, db, conversation.id, 3)

        mock_llm.generate = AsyncMock(return_value="Ringkasan turn 2.")
        context = await service.build_conversation_context(conversation.id, recent_limit=4)
        await db.commit()

    assert mock_llm.generate.call_count == 1
    sent_messages = mock_llm.generate.call_args.kwargs["messages"]
    system_content = sent_messages[0]["content"]
    user_content = sent_messages[1]["content"]
    assert "running summary" in system_content.lower()
    assert "Ringkasan turn 1." in user_content  # prior summary passed in, not regenerated
    assert "q1" in user_content
    assert "a1" in user_content
    assert "q0" not in user_content  # NOT resent — already folded in last turn
    assert "a0" not in user_content
    assert "Ringkasan turn 2." in context


async def test_repeated_call_with_no_new_aged_out_messages_skips_the_llm(
    client_factory,
) -> None:
    organization_id, user_id = await _register_and_get_ids(client_factory)
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="Ringkasan.")
    async with async_session_factory() as db:
        service = ConversationService(db, llm_gateway=mock_llm)
        conversation = await service.create_conversation(organization_id, user_id)
        for i in range(3):
            await _append_turn(service, db, conversation.id, i)

        await service.build_conversation_context(conversation.id, recent_limit=4)
        await db.commit()

        mock_llm.generate.reset_mock()
        # Calling again with no messages appended in between must not
        # re-summarize anything — nothing new aged out of the window.
        context = await service.build_conversation_context(conversation.id, recent_limit=4)

    mock_llm.generate.assert_not_called()
    assert "Ringkasan." in context
