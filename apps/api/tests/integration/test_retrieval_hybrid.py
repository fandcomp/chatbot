"""Hybrid retrieval: dense + sparse in parallel, RRF-fused (spec §29.2/§32,
§97's "hybrid semantic retrieval"). Uses a real Qdrant instance (this
codebase's shared "document_chunks" collection) with the Voyage embedding
call mocked, mirroring workers/document_worker/tests/test_index_document.py.

Requires `docker compose up -d` to be running from the repo root.
"""

from unittest.mock import AsyncMock, patch

from qdrant_client import models

from app.core.config import settings
from app.core.database import async_session_factory
from app.indexing.qdrant_client import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_client,
)
from app.parsing.models import DocumentNodeType
from app.retrieval.sparse_vector import build_sparse_vector

from ._retrieval_fixtures import (
    resolve_organization_id,
    seed_active_document,
    seed_node_and_chunk,
)

REGISTER_PAYLOAD = {
    "organization_name": "Hybrid Retrieval Test Org",
    "email": "owner@hybrid-retrieval-test.io",
    "password": "supersecret123",
}

_TEXT = "Setiap penyelenggara wajib melakukan mitigasi risiko bencana secara berkala."


async def _ensure_collection(client) -> None:
    if not await client.collection_exists(COLLECTION_NAME):
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                DENSE_VECTOR_NAME: models.VectorParams(
                    size=settings.VOYAGE_EMBEDDING_DIMENSION, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )


async def test_hybrid_search_fuses_dense_and_sparse_with_tenant_filter(client_factory) -> None:
    # Arrange
    client = client_factory()
    await client.post("/auth/register", json=REGISTER_PAYLOAD)
    ks_id = (await client.get("/knowledge-spaces")).json()[0]["id"]

    async with async_session_factory() as db:
        org_id = await resolve_organization_id(db, ks_id)
        document_id, version_id, region_id = await seed_active_document(db, org_id, ks_id)
        _node_id, chunk_id = await seed_node_and_chunk(
            db,
            org_id,
            document_id,
            version_id,
            region_id,
            node_type=DocumentNodeType.PARAGRAPH,
            sequence_number=0,
            original_text=_TEXT,
            structural_path_json=[{"type": "SECTION", "label": "1", "title": None}],
            structural_path_text="1",
        )
        await db.commit()

    dense_vector = [0.1] * settings.VOYAGE_EMBEDDING_DIMENSION
    sparse_indices, sparse_values = build_sparse_vector(_TEXT)

    qdrant = get_qdrant_client()
    await _ensure_collection(qdrant)
    await qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=str(chunk_id),
                vector={
                    DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=sparse_indices, values=sparse_values
                    ),
                },
                payload={
                    "organization_id": str(org_id),
                    "knowledge_space_id": str(ks_id),
                    "document_id": str(document_id),
                    "document_version_id": str(version_id),
                    "document_status": "ACTIVE",
                    "chunk_id": str(chunk_id),
                },
            )
        ],
    )
    await qdrant.close()

    try:
        fake_result = AsyncMock()
        fake_result.results = [AsyncMock(embeddings=[dense_vector])]
        with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.contextualized_embed = AsyncMock(
                return_value=fake_result
            )
            response = await client.post(
                "/retrieval/search", json={"query": "mitigasi risiko bencana"}
            )

        # Assert
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "HYBRID"
        assert len(body["chunks"]) == 1
        assert body["chunks"][0]["chunk_id"] == str(chunk_id)
        assert body["chunks"][0]["score"] is not None
    finally:
        cleanup_client = get_qdrant_client()
        await cleanup_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=str(document_id))
                    )
                ]
            ),
        )
        await cleanup_client.close()


async def test_hybrid_search_excludes_other_organizations_points(client_factory) -> None:
    # Arrange — a point that exists in Qdrant but belongs to a different
    # organization_id must never surface even with an identical dense vector
    # and matching sparse terms (ADR-009's mandatory tenant filter).
    client = client_factory()
    await client.post(
        "/auth/register",
        json={
            "organization_name": "Hybrid Isolation Org",
            "email": "owner@hybrid-isolation.io",
            "password": "supersecret123",
        },
    )
    other_org_id = "00000000-0000-0000-0000-000000000099"
    fake_chunk_id = "00000000-0000-0000-0000-000000000098"
    dense_vector = [0.2] * settings.VOYAGE_EMBEDDING_DIMENSION
    sparse_indices, sparse_values = build_sparse_vector(_TEXT)

    qdrant = get_qdrant_client()
    await _ensure_collection(qdrant)
    await qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=fake_chunk_id,
                vector={
                    DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=sparse_indices, values=sparse_values
                    ),
                },
                payload={
                    "organization_id": other_org_id,
                    "document_status": "ACTIVE",
                    "chunk_id": fake_chunk_id,
                },
            )
        ],
    )
    await qdrant.close()

    try:
        fake_result = AsyncMock()
        fake_result.results = [AsyncMock(embeddings=[dense_vector])]
        with patch("app.retrieval.embedding_gateway.voyageai.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.contextualized_embed = AsyncMock(
                return_value=fake_result
            )
            response = await client.post(
                "/retrieval/search", json={"query": "mitigasi risiko bencana"}
            )

        # Assert
        assert response.status_code == 200
        assert response.json()["chunks"] == []
    finally:
        cleanup_client = get_qdrant_client()
        await cleanup_client.delete(
            collection_name=COLLECTION_NAME, points_selector=models.PointIdsList(points=[fake_chunk_id])
        )
        await cleanup_client.close()
