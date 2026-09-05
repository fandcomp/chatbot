"""M8 reranking end-to-end: conditional Voyage rerank, graceful degradation
on reranker failure, and parent expansion (spec §33/§23, §97's "conditional
reranking").

Requires `docker compose up -d` to be running from the repo root.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.chunking.models import DocumentChunk
from app.core.database import async_session_factory
from app.parsing.models import DocumentNodeType

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Reranking Test Org",
    "email": "owner@reranking-test.io",
    "password": "supersecret123",
}


async def _register_and_get_space(client_factory):
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    return client, ks_id


def _rerank_result(pairs: list[tuple[int, float]]) -> SimpleNamespace:
    return SimpleNamespace(
        results=[SimpleNamespace(index=index, relevance_score=score) for index, score in pairs]
    )


async def test_exact_match_skips_reranking(client_factory) -> None:
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
            original_text="Pasal 3\nKetentuan tunggal.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 3", "title": None}],
            structural_path_text="Pasal 3",
            article_number="3",
        )
        await db.commit()

    # Act — no Voyage mock installed at all: if this reached the reranker it
    # would raise (no API call should ever be attempted here).
    response = await client.post("/reranking/evidence", json={"query": "Pasal 3"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_mode"] == "EXACT_STRUCTURAL"
    assert body["reranked"] is False
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["evidence_id"] == "S1"
    assert "Ketentuan tunggal" in body["evidence"][0]["original_text"]


async def test_multi_document_candidates_trigger_reranking_and_reorder(client_factory) -> None:
    # Arrange — two ACTIVE documents, each with one exact-generic-path chunk
    # sharing the same structural label, so both surface via the same
    # GENERIC_PATH match and confidence.needs_reranking's multi-document
    # branch fires.
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        for label_suffix in ("A", "B"):
            document_id, version_id, region_id = await seed_active_document(
                db, org_id, ks_id, title=f"Doc {label_suffix}"
            )
            await seed_node_and_chunk(
                db,
                org_id,
                document_id,
                version_id,
                region_id,
                node_type=DocumentNodeType.NUMBERED_SECTION,
                sequence_number=0,
                original_text=f"Isi angka 7 dokumen {label_suffix}.",
                structural_path_json=[{"type": "NUMBERED_SECTION", "label": "7", "title": None}],
                structural_path_text="7",
                number_raw="7.",
                number_normalized="7",
            )
        await db.commit()

    # Act — mock Voyage to reverse the order (second candidate wins).
    with patch("app.reranking.reranker_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.rerank = AsyncMock(
            return_value=_rerank_result([(1, 0.9), (0, 0.4)])
        )
        response = await client.post("/reranking/evidence", json={"query": "angka 7"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_mode"] == "EXACT_STRUCTURAL"
    assert body["reranked"] is True
    assert len(body["evidence"]) == 2
    assert body["evidence"][0]["relevance_score"] == 0.9
    assert body["evidence"][1]["relevance_score"] == 0.4


async def test_reranker_failure_falls_back_to_unreranked_evidence(client_factory) -> None:
    # Arrange — same multi-document setup as above.
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        for label_suffix in ("A", "B"):
            document_id, version_id, region_id = await seed_active_document(
                db, org_id, ks_id, title=f"Doc {label_suffix}"
            )
            await seed_node_and_chunk(
                db,
                org_id,
                document_id,
                version_id,
                region_id,
                node_type=DocumentNodeType.NUMBERED_SECTION,
                sequence_number=0,
                original_text=f"Isi angka 8 dokumen {label_suffix}.",
                structural_path_json=[{"type": "NUMBERED_SECTION", "label": "8", "title": None}],
                structural_path_text="8",
                number_raw="8.",
                number_normalized="8",
            )
        await db.commit()

    # Act — Voyage rerank raises; must degrade gracefully, not 500.
    with patch("app.reranking.reranker_gateway.voyageai.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.rerank = AsyncMock(side_effect=RuntimeError("Voyage down"))
        response = await client.post("/reranking/evidence", json={"query": "angka 8"})

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["reranked"] is False
    assert len(body["evidence"]) == 2


async def test_small_fragment_expands_with_parent_context(client_factory) -> None:
    # Arrange — an ARTICLE parent chunk, and a small CLAUSE child chunk
    # (well under the expansion threshold) pointing at it via
    # parent_chunk_id.
    client, ks_id = await _register_and_get_space(client_factory)
    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        _parent_node_id, parent_chunk_id = await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.ARTICLE,
            sequence_number=0,
            original_text="Pasal 12\nKetentuan mengenai perizinan.",
            structural_path_json=[{"type": "ARTICLE", "label": "Pasal 12", "title": None}],
            structural_path_text="Pasal 12",
            article_number="12",
        )
        _child_node_id, child_chunk_id = await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.CLAUSE,
            sequence_number=1,
            original_text="Ya.",
            structural_path_json=[
                {"type": "ARTICLE", "label": "Pasal 12", "title": None},
                {"type": "CLAUSE", "label": "1", "title": None},
            ],
            structural_path_text="Pasal 12 > 1",
            article_number="12",
            clause_number="1",
        )
        # seed_node_and_chunk never sets parent_chunk_id — wire it directly
        # for this test's specific parent/child relationship.
        child = (
            await db.execute(select(DocumentChunk).where(DocumentChunk.id == child_chunk_id))
        ).scalar_one()
        child.parent_chunk_id = parent_chunk_id
        child.token_count = 2
        await db.commit()

    # Act
    response = await client.post(
        "/reranking/evidence", json={"query": "Apa isi Pasal 12 ayat 1?"}
    )

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["original_text"] == "Ya."
    assert body["evidence"][0]["parent_context"] is not None
    assert "perizinan" in body["evidence"][0]["parent_context"]
