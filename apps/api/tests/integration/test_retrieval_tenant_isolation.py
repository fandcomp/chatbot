"""Cross-org leakage and non-ACTIVE exclusion for retrieval (ADR-009, §97's
"tenant isolation" / "archived document not retrievable" / "deleted document
not retrievable" mandatory test cases).

Requires `docker compose up -d` to be running from the repo root.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import async_session_factory
from app.documents.models import DocumentLifecycleStatus
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_lan_source_entry,
    seed_node_and_chunk,
)


@contextmanager
def _mocked_voyage():
    # These tests exercise the fallback-to-HYBRID path for non-ACTIVE/deleted
    # documents — they must never spend a real Voyage API call just to prove
    # exclusion (worker's test_embedding_gateway.py convention).
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        yield

ORG_A_PAYLOAD = {
    "organization_name": "Retrieval Isolation Org A",
    "email": "owner@retrieval-isolation-a.io",
    "password": "supersecret123",
}
ORG_B_PAYLOAD = {
    "organization_name": "Retrieval Isolation Org B",
    "email": "owner@retrieval-isolation-b.io",
    "password": "supersecret123",
}

_ARTICLE_PATH = [{"type": "ARTICLE", "label": "Pasal 9", "title": None}]


async def _seed_article(client_factory, payload: dict, status: DocumentLifecycleStatus):
    client = client_factory()
    await client.post("/auth/register", json=payload)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(
            db, org_id, ks_id, status=status
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 9\nKetentuan rahasia organisasi ini.",
            structural_path_json=_ARTICLE_PATH,
            structural_path_text="Pasal 9",
            article_number="9",
        )
        await db.commit()

    return client, document_id


async def _seed_lan_sourced_article(client_factory, payload: dict, status: DocumentLifecycleStatus):
    # LAN-M4: same seeding as _seed_article, but the version carries a real
    # source_entry_id — proves retrieval/revocation never branch on document
    # provenance (there is no such branch anywhere in the codebase; this is
    # the regression test for that claim, not a claim on its own).
    client = client_factory()
    await client.post("/auth/register", json=payload)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        source_entry_id = await seed_lan_source_entry(db, org_id, ks_id)
        document_id, version_id, region_id = await seed_active_document(
            db, org_id, ks_id, status=status, source_entry_id=source_entry_id
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 9\nKetentuan rahasia organisasi ini.",
            structural_path_json=_ARTICLE_PATH,
            structural_path_text="Pasal 9",
            article_number="9",
        )
        await db.commit()

    return client, document_id


async def test_org_a_cannot_exact_match_org_bs_lan_sourced_article(client_factory) -> None:
    # Arrange
    client_a, _ = await _seed_lan_sourced_article(
        client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.ACTIVE
    )
    _, org_b_document_id = await _seed_lan_sourced_article(
        client_factory, ORG_B_PAYLOAD, DocumentLifecycleStatus.ACTIVE
    )

    # Act
    response = await client_a.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert — identical guarantee to an uploaded document: org A never sees
    # org B's LAN-sourced content.
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "EXACT_STRUCTURAL"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["document_id"] != str(org_b_document_id)


async def test_archiving_a_lan_sourced_document_revokes_it_immediately(client_factory) -> None:
    # LAN-M4 (addendum §7): "revocation that takes effect immediately,
    # independent of the ingestion cycle" — proves the existing archive
    # endpoint already delivers this for a LAN-promoted document, with no
    # dependency on a rescan/reconciliation job ever running.
    client, document_id = await _seed_lan_sourced_article(
        client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.ACTIVE
    )
    precondition = await client.post("/retrieval/search", json={"query": "Pasal 9"})
    assert precondition.json()["mode"] == "EXACT_STRUCTURAL"  # sanity check

    # Act
    archive_response = await client.post(f"/documents/{document_id}/archive")
    with _mocked_voyage():
        search_response = await client.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "ARCHIVED"
    body = search_response.json()
    assert body["mode"] != "EXACT_STRUCTURAL"
    assert body["chunks"] == []


async def test_org_a_cannot_exact_match_org_bs_article(client_factory) -> None:
    # Arrange
    client_a, _ = await _seed_article(client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.ACTIVE)
    _, org_b_document_id = await _seed_article(
        client_factory, ORG_B_PAYLOAD, DocumentLifecycleStatus.ACTIVE
    )

    # Act
    response = await client_a.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert — org A has its own Pasal 9, so it must get exactly its own
    # text, never org B's.
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "EXACT_STRUCTURAL"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["document_id"] != str(org_b_document_id)


async def test_archived_document_not_retrievable(client_factory) -> None:
    # Arrange
    client, _ = await _seed_article(
        client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.ARCHIVED
    )

    # Act
    with _mocked_voyage():
        response = await client.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert — ARCHIVED is not ACTIVE, so the exact-match SQL filter must
    # exclude it entirely (never falls back to a stale exact hit).
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] != "EXACT_STRUCTURAL"
    assert body["chunks"] == []


async def test_superseded_document_not_retrievable(client_factory) -> None:
    # Arrange
    client, _ = await _seed_article(
        client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.SUPERSEDED
    )

    # Act
    with _mocked_voyage():
        response = await client.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] != "EXACT_STRUCTURAL"
    assert body["chunks"] == []


async def test_deleted_document_not_retrievable(client_factory) -> None:
    # Arrange
    client, document_id = await _seed_article(
        client_factory, ORG_A_PAYLOAD, DocumentLifecycleStatus.ACTIVE
    )
    precondition = await client.post("/retrieval/search", json={"query": "Pasal 9"})
    assert precondition.json()["mode"] == "EXACT_STRUCTURAL"  # sanity check

    # Act
    delete_response = await client.delete(f"/documents/{document_id}")
    with _mocked_voyage():
        search_response = await client.post("/retrieval/search", json={"query": "Pasal 9"})

    # Assert
    assert delete_response.status_code == 204
    body = search_response.json()
    assert body["mode"] != "EXACT_STRUCTURAL"
    assert body["chunks"] == []
