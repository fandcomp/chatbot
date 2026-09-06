"""Unit tests for AnalyticsService (spec §62-63, §92): QueryLog persistence,
KnowledgeGap upsert-by-normalized-query, and the overview aggregation math.
Hits real Postgres directly via async_session_factory (no HTTP layer) —
mirrors tests/unit/test_structure_rbac.py's DB-seeding convention.

Requires `docker compose up -d` to be running from the repo root.
"""

import uuid
from datetime import UTC, datetime

from app.analytics.models import (
    Feedback,
    FeedbackRating,
    KnowledgeGap,
    QueryLog,
    QueryLogSource,
)
from app.analytics.service import AnalyticsService
from app.chat.models import Conversation, Message, MessageRole, MessageSource
from app.chat.service import ConversationService
from app.core.database import async_session_factory
from app.organizations.models import Organization
from app.parsing.models import DocumentNodeType
from app.users.models import User

from ..integration._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Analytics Test Org",
    "email": "owner@analytics-test.io",
    "password": "supersecret123",
}


async def _register(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    async with async_session_factory() as db:
        org = (await db.execute(Organization.__table__.select())).mappings().first()
        organization_id = org["id"]
        user = (await db.execute(User.__table__.select())).mappings().first()
        user_id = user["id"]
    return organization_id, user_id


async def _register_with_knowledge_space(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    async with async_session_factory() as db:
        organization_id = await resolve_organization_id(db, ks_id)
        user = (await db.execute(User.__table__.select())).mappings().first()
        user_id = user["id"]
    return organization_id, user_id, ks_id


async def _log(
    service: AnalyticsService,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    source: QueryLogSource = QueryLogSource.CHAT,
    insufficient_evidence: bool = False,
    query_text: str = "Apa isi Pasal 5?",
    citation_count: int = 1,
    retrieved_source_count: int = 1,
    tier: str | None = "FAST",
    input_tokens: int | None = 10,
    output_tokens: int | None = 20,
) -> None:
    await service.log_query(
        organization_id=organization_id,
        user_id=user_id,
        conversation_id=None,
        source=source,
        query_text=query_text,
        retrieval_mode="EXACT_STRUCTURAL",
        reranked=False,
        tier=tier,
        insufficient_evidence=insufficient_evidence,
        retrieved_source_count=retrieved_source_count,
        citation_count=citation_count,
        retrieval_latency_ms=50,
        llm_latency_ms=100,
        total_latency_ms=150,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def test_log_query_persists_a_query_log_row(client_factory) -> None:
    # Arrange
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        await _log(AnalyticsService(db), organization_id, user_id)
        await db.commit()

    # Assert
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                QueryLog.__table__.select().where(QueryLog.organization_id == organization_id)
            )
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["source"] == QueryLogSource.CHAT
    assert rows[0]["total_latency_ms"] == 150
    assert rows[0]["estimated_cost_usd"] is not None or rows[0]["estimated_cost_usd"] == 0


async def test_log_query_with_insufficient_evidence_creates_a_knowledge_gap(
    client_factory,
) -> None:
    # Arrange
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        await _log(
            AnalyticsService(db),
            organization_id,
            user_id,
            insufficient_evidence=True,
            query_text="  Apa Isi PASAL 999?  ",
        )
        await db.commit()

    # Assert
    async with async_session_factory() as db:
        gaps = (
            await db.execute(
                KnowledgeGap.__table__.select().where(
                    KnowledgeGap.organization_id == organization_id
                )
            )
        ).mappings().all()
    assert len(gaps) == 1
    assert gaps[0]["frequency"] == 1
    assert gaps[0]["normalized_query"] == "apa isi pasal 999?"


async def test_repeated_insufficient_evidence_query_increments_existing_gap(
    client_factory,
) -> None:
    # Arrange — same question asked twice, differently cased/spaced.
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        service = AnalyticsService(db)
        await _log(
            service, organization_id, user_id, insufficient_evidence=True,
            query_text="Apa isi Pasal 999?",
        )
        await _log(
            service, organization_id, user_id, insufficient_evidence=True,
            query_text="apa   isi pasal 999?",
        )
        await db.commit()

    # Assert
    async with async_session_factory() as db:
        gaps = (
            await db.execute(
                KnowledgeGap.__table__.select().where(
                    KnowledgeGap.organization_id == organization_id
                )
            )
        ).mappings().all()
    assert len(gaps) == 1
    assert gaps[0]["frequency"] == 2


async def test_get_overview_excludes_test_knowledge_traffic(client_factory) -> None:
    # Arrange — one real chat turn, one Test Knowledge preview turn.
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        service = AnalyticsService(db)
        await _log(service, organization_id, user_id, source=QueryLogSource.CHAT)
        await _log(
            service, organization_id, user_id, source=QueryLogSource.TEST_KNOWLEDGE,
            query_text="Admin preview query",
        )
        await db.commit()
        overview = await service.get_overview(organization_id)

    # Assert
    assert overview.total_questions == 1
    assert overview.answered == 1
    assert overview.citation_coverage == 1.0
    assert overview.retrieval_success == 1.0


async def test_get_overview_computes_feedback_counts(client_factory) -> None:
    # Arrange
    organization_id, user_id = await _register(client_factory)
    async with async_session_factory() as db:
        chatbot = await ConversationService(db).get_or_create_default_chatbot(organization_id)
        conversation = Conversation(
            organization_id=organization_id,
            chatbot_id=chatbot.id,
            user_id=user_id,
            title="t",
        )
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="answer",
        )
        db.add(message)
        await db.flush()
        db.add(
            Feedback(
                organization_id=organization_id,
                message_id=message.id,
                user_id=user_id,
                rating=FeedbackRating.THUMBS_UP,
            )
        )
        db.add(
            Feedback(
                organization_id=organization_id,
                message_id=message.id,
                user_id=user_id,
                rating=FeedbackRating.THUMBS_DOWN,
            )
        )
        await db.commit()

    # Act
    async with async_session_factory() as db:
        overview = await AnalyticsService(db).get_overview(organization_id)

    # Assert
    assert overview.thumbs_up == 1
    assert overview.thumbs_down == 1


async def test_every_chat_query_is_tracked_in_question_frequency_regardless_of_outcome(
    client_factory,
) -> None:
    # Arrange — one answered question, one insufficient-evidence question;
    # spec §63's "top topics" tracks both, unlike KnowledgeGap (§62).
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        service = AnalyticsService(db)
        await _log(service, organization_id, user_id, insufficient_evidence=False)
        await _log(
            service, organization_id, user_id, insufficient_evidence=True,
            query_text="Pertanyaan lain",
        )
        await db.commit()
        questions = await service.list_top_questions(organization_id)

    # Assert
    assert {q.sample_query_text for q in questions} == {
        "Apa isi Pasal 5?",
        "Pertanyaan lain",
    }


async def test_test_knowledge_queries_are_not_tracked_in_question_frequency(
    client_factory,
) -> None:
    # Arrange
    organization_id, user_id = await _register(client_factory)

    # Act
    async with async_session_factory() as db:
        service = AnalyticsService(db)
        await _log(service, organization_id, user_id, source=QueryLogSource.TEST_KNOWLEDGE)
        await db.commit()
        questions = await service.list_top_questions(organization_id)

    # Assert
    assert questions == []


async def _add_message_source(
    db, conversation, document_id: uuid.UUID, chunk_id: uuid.UUID, source_label: str = "S1"
) -> None:
    message = Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content="a")
    db.add(message)
    await db.flush()
    db.add(
        MessageSource(
            message_id=message.id,
            source_label=source_label,
            chunk_id=chunk_id,
            document_id=document_id,
            structural_path_text="Pasal 5",
            page_start=1,
            page_end=1,
        )
    )
    await db.flush()


async def test_list_top_documents_counts_and_ranks_citations(client_factory) -> None:
    # Arrange — document A cited twice, document B cited once. Real
    # Document/DocumentChunk rows are required: MessageSource.chunk_id and
    # .document_id are real foreign keys.
    organization_id, user_id, ks_id = await _register_with_knowledge_space(client_factory)
    async with async_session_factory() as db:
        doc_a_id, version_a, region_a = await seed_active_document(db, organization_id, ks_id, title="Doc A")
        _node_a, chunk_a = await seed_node_and_chunk(
            db, organization_id, doc_a_id, version_a, region_a,
            node_type=DocumentNodeType.ARTICLE, sequence_number=0,
            original_text="Pasal 5", structural_path_json=[{"type": "ARTICLE", "label": "Pasal 5"}],
            structural_path_text="Pasal 5", article_number="5",
        )
        doc_b_id, version_b, region_b = await seed_active_document(db, organization_id, ks_id, title="Doc B")
        _node_b, chunk_b = await seed_node_and_chunk(
            db, organization_id, doc_b_id, version_b, region_b,
            node_type=DocumentNodeType.ARTICLE, sequence_number=0,
            original_text="Pasal 6", structural_path_json=[{"type": "ARTICLE", "label": "Pasal 6"}],
            structural_path_text="Pasal 6", article_number="6",
        )

        chatbot = await ConversationService(db).get_or_create_default_chatbot(organization_id)
        conversation = Conversation(
            organization_id=organization_id, chatbot_id=chatbot.id, user_id=user_id, title="t"
        )
        db.add(conversation)
        await db.flush()

        await _add_message_source(db, conversation, doc_a_id, chunk_a)
        await _add_message_source(db, conversation, doc_a_id, chunk_a)
        await _add_message_source(db, conversation, doc_b_id, chunk_b)
        await db.commit()

    # Act
    async with async_session_factory() as db:
        documents = await AnalyticsService(db).list_top_documents(organization_id)

    # Assert
    assert documents[0].document_id == doc_a_id
    assert documents[0].citation_count == 2
    assert documents[0].document_title == "Doc A"
    assert documents[1].document_id == doc_b_id
    assert documents[1].citation_count == 1


async def test_list_knowledge_gaps_orders_by_frequency_descending(client_factory) -> None:
    # Arrange
    organization_id, _user_id = await _register(client_factory)
    async with async_session_factory() as db:
        db.add(
            KnowledgeGap(
                organization_id=organization_id,
                normalized_query="rare question",
                sample_query_text="Rare question",
                frequency=1,
                last_asked_at=datetime.now(UTC),
            )
        )
        db.add(
            KnowledgeGap(
                organization_id=organization_id,
                normalized_query="common question",
                sample_query_text="Common question",
                frequency=5,
                last_asked_at=datetime.now(UTC),
            )
        )
        await db.commit()

    # Act
    async with async_session_factory() as db:
        gaps = await AnalyticsService(db).list_knowledge_gaps(organization_id)

    # Assert
    assert [gap.sample_query_text for gap in gaps] == ["Common question", "Rare question"]
