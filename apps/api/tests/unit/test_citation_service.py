"""Unit tests for AdaptiveCitationService's relation enrichment (spec §21,
ADR-018's sibling feature). Against the real Postgres instance (`docker
compose up -d`), same pattern as test_structure_rbac.py.
"""

import uuid

import pytest_asyncio
from sqlalchemy import delete

from app.citations.service import AdaptiveCitationService
from app.core.database import async_session_factory
from app.documents.models import (
    Document,
    DocumentLifecycleStatus,
    DocumentRelation,
    DocumentRelationType,
    DocumentVersion,
)
from app.knowledge.models import KnowledgeSpace
from app.organizations.models import Organization
from app.reranking.schemas import Evidence


def _evidence(document_id: uuid.UUID, evidence_id: str = "S1") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        document_version_id=uuid.uuid4(),
        structural_path_text="Pasal 5",
        original_text="Ketentuan umum.",
        page_start=1,
        page_end=1,
        parent_context=None,
        relevance_score=None,
    )


@pytest_asyncio.fixture
async def _two_documents():
    org_id = uuid.uuid4()
    space_id = uuid.uuid4()
    cited_doc_id = uuid.uuid4()
    amending_doc_id = uuid.uuid4()
    cited_version_id = uuid.uuid4()
    amending_version_id = uuid.uuid4()

    async with async_session_factory() as session:
        # No relationship() is declared between these models (documents/
        # models.py's own comment on this), so the ORM's unit-of-work has no
        # FK dependency graph to order inserts across tables automatically —
        # each table must be flushed before the next one that references it.
        session.add(Organization(id=org_id, name="Relation Test Org", slug=f"rel-test-{org_id}"))
        await session.flush()
        session.add(KnowledgeSpace(id=space_id, organization_id=org_id, name="General"))
        await session.flush()
        session.add(
            Document(
                id=cited_doc_id,
                organization_id=org_id,
                knowledge_space_id=space_id,
                title="Regulation A (Cited)",
            )
        )
        session.add(
            Document(
                id=amending_doc_id,
                organization_id=org_id,
                knowledge_space_id=space_id,
                title="Regulation B (Amends A)",
            )
        )
        await session.flush()
        session.add(
            DocumentVersion(
                id=cited_version_id,
                organization_id=org_id,
                document_id=cited_doc_id,
                version_number=1,
                file_hash="a" * 64,
                original_filename="a.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                storage_path="unused/a.pdf",
                status=DocumentLifecycleStatus.ACTIVE,
            )
        )
        session.add(
            DocumentVersion(
                id=amending_version_id,
                organization_id=org_id,
                document_id=amending_doc_id,
                version_number=1,
                file_hash="b" * 64,
                original_filename="b.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                storage_path="unused/b.pdf",
                status=DocumentLifecycleStatus.ACTIVE,
            )
        )
        await session.commit()

    yield {
        "org_id": org_id,
        "cited_doc_id": cited_doc_id,
        "amending_doc_id": amending_doc_id,
        "cited_version_id": cited_version_id,
        "amending_version_id": amending_version_id,
    }

    async with async_session_factory() as session:
        await session.execute(delete(DocumentRelation).where(DocumentRelation.organization_id == org_id))
        await session.execute(delete(DocumentVersion).where(DocumentVersion.organization_id == org_id))
        await session.execute(delete(Document).where(Document.organization_id == org_id))
        await session.execute(delete(KnowledgeSpace).where(KnowledgeSpace.organization_id == org_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()


async def test_citation_carries_no_relations_when_none_exist(_two_documents) -> None:
    seeded = _two_documents
    async with async_session_factory() as session:
        citations = await AdaptiveCitationService(session).build_citations(
            [_evidence(seeded["cited_doc_id"])], seeded["org_id"]
        )
    assert citations["S1"].superseding_relations == []


async def test_citation_never_leaks_a_title_or_relation_from_another_organization(
    _two_documents,
) -> None:
    # Defense-in-depth: even though evidence.document_id is already
    # tenant-scoped upstream by RetrievalService, this service must not
    # trust that blindly — passing the WRONG organization_id must yield
    # "(unknown document)" and no relations, never real data.
    seeded = _two_documents
    async with async_session_factory() as session:
        session.add(
            DocumentRelation(
                organization_id=seeded["org_id"],
                from_document_version_id=seeded["amending_version_id"],
                to_document_version_id=seeded["cited_version_id"],
                relation_type=DocumentRelationType.AMENDS,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        citations = await AdaptiveCitationService(session).build_citations(
            [_evidence(seeded["cited_doc_id"])], uuid.uuid4()
        )
    assert citations["S1"].document_title == "(unknown document)"
    assert citations["S1"].superseding_relations == []


async def test_citation_surfaces_an_amends_relation_on_the_cited_document(_two_documents) -> None:
    seeded = _two_documents
    async with async_session_factory() as session:
        session.add(
            DocumentRelation(
                organization_id=seeded["org_id"],
                from_document_version_id=seeded["amending_version_id"],
                to_document_version_id=seeded["cited_version_id"],
                relation_type=DocumentRelationType.AMENDS,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        citations = await AdaptiveCitationService(session).build_citations(
            [_evidence(seeded["cited_doc_id"])], seeded["org_id"]
        )

    relations = citations["S1"].superseding_relations
    assert len(relations) == 1
    assert relations[0].relation_type == DocumentRelationType.AMENDS
    assert relations[0].related_document_id == seeded["amending_doc_id"]
    assert relations[0].related_document_title == "Regulation B (Amends A)"


async def test_citation_is_unaffected_by_a_refers_to_relation(_two_documents) -> None:
    # REFERS_TO is a plain cross-reference, not a staleness signal — must
    # never trigger the citation warning.
    seeded = _two_documents
    async with async_session_factory() as session:
        session.add(
            DocumentRelation(
                organization_id=seeded["org_id"],
                from_document_version_id=seeded["amending_version_id"],
                to_document_version_id=seeded["cited_version_id"],
                relation_type=DocumentRelationType.REFERS_TO,
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        citations = await AdaptiveCitationService(session).build_citations(
            [_evidence(seeded["cited_doc_id"])], seeded["org_id"]
        )
    assert citations["S1"].superseding_relations == []
