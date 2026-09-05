"""Exact structural retrieval (spec §29.1, §97's "exact Pasal retrieval" /
"exact Pasal + Ayat retrieval", addendum §23's generic-path priority).

Requires `docker compose up -d` to be running from the repo root.
"""

from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import async_session_factory
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Retrieval Test Org",
    "email": "owner@retrieval-test.io",
    "password": "supersecret123",
}


async def _register_and_get_space(client_factory) -> tuple:
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    knowledge_space_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, knowledge_space_id


async def test_exact_article_retrieval(client_factory) -> None:
    # Arrange
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 17\nSetiap warga negara berhak atas pendidikan.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 17", "title": None}],
            structural_path_text="Pasal 17",
            article_number="17",
        )
        await db.commit()

    # Act
    response = await client.post("/retrieval/search", json={"query": "Apa isi Pasal 17?"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "EXACT_STRUCTURAL"
    assert len(body["chunks"]) == 1
    assert "Pasal 17" in body["chunks"][0]["original_text"]


async def test_exact_article_and_clause_retrieval(client_factory) -> None:
    # Arrange
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 5\nKetentuan umum.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 5", "title": None}],
            structural_path_text="Pasal 5",
            article_number="5",
        )
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.CLAUSE,
            sequence_number=1,
            original_text="Pasal 5 ayat (2)\nSetiap orang wajib mendaftar.",
            structural_path_json=[
                {"type": "ARTICLE", "label": "Pasal 5", "title": None},
                {"type": "CLAUSE", "label": "2", "title": None},
            ],
            structural_path_text="Pasal 5 > 2",
            article_number="5",
            clause_number="2",
        )
        await db.commit()

    # Act
    response = await client.post("/retrieval/search", json={"query": "Apa isi Pasal 5 ayat 2?"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "EXACT_STRUCTURAL"
    assert len(body["chunks"]) == 1
    assert "wajib mendaftar" in body["chunks"][0]["original_text"]


async def test_exact_generic_path_retrieval_for_non_article_source(client_factory) -> None:
    # Arrange — a numbered-guideline source with no Pasal at all (addendum
    # §16's canonical example): "BAB III > 11 Urut-urutan Kegiatan > a".
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.LETTER_ITEM,
            sequence_number=0,
            original_text="a. Menyusun rencana kerja tahunan.",
            structural_path_json=[
                {"type": "CHAPTER", "label": "BAB III", "title": "TAHAP PERENCANAAN"},
                {"type": "NUMBERED_SECTION", "label": "11", "title": "Urut-urutan Kegiatan"},
                {"type": "LETTER_ITEM", "label": "a", "title": None},
            ],
            structural_path_text="BAB III > 11 Urut-urutan Kegiatan > a",
            structural_depth=3,
            number_raw="a.",
            number_normalized="a",
        )
        await db.commit()

    # Act
    response = await client.post("/retrieval/search", json={"query": "angka 11 huruf a"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "EXACT_STRUCTURAL"
    assert len(body["chunks"]) == 1
    assert "rencana kerja tahunan" in body["chunks"][0]["original_text"]


async def test_never_fabricates_pasal_falls_back_when_no_article_exists(client_factory) -> None:
    # A user asking for "Pasal 11" against a numbered-guideline-only source
    # (no ARTICLE nodes at all) must not get a fabricated exact hit — the
    # parser recognizes ARTICLE kind, but no matching row exists, so this
    # falls through to hybrid search rather than crashing or lying.
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.NUMBERED_SECTION,
            sequence_number=0,
            original_text="11. Urut-urutan Kegiatan.",
            structural_path_json=[{"type": "NUMBERED_SECTION", "label": "11", "title": None}],
            structural_path_text="11",
            number_raw="11.",
            number_normalized="11",
        )
        await db.commit()

    # Act — mock the Voyage call (worker's test_embedding_gateway.py
    # convention): this test must never spend a real Voyage API call just to
    # prove a fallback-mode decision.
    fake_result = AsyncMock()
    fake_result.results = [AsyncMock(embeddings=[[0.0] * settings.VOYAGE_EMBEDDING_DIMENSION])]
    with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.contextualized_embed = AsyncMock(return_value=fake_result)
        response = await client.post("/retrieval/search", json={"query": "Pasal 11"})

    # Assert — no ARTICLE rows exist, so this must not be EXACT_STRUCTURAL;
    # it degrades to HYBRID (empty in this test's minimal fixture since
    # nothing was ever indexed into Qdrant, but must never claim an exact
    # match it doesn't have).
    assert response.status_code == 200
    assert response.json()["mode"] == "HYBRID"
