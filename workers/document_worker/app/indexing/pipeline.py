"""Orchestrates M6: embed each version's chunks (dense), build sparse
vectors and payloads, and produce Qdrant points ready to upsert. Never
re-chunks — reads M5's already-persisted `document_chunks` rows as-is.
"""

from dataclasses import dataclass

from qdrant_client import models

from app.database import async_session_factory
from app.indexing.embedding_cache import (
    cache_key_for,
    get_cached_embeddings,
    store_embeddings,
)
from app.indexing.embedding_gateway import EmbeddingGateway
from app.indexing.payload_builder import build_chunk_payload
from app.indexing.sparse_vector import build_sparse_vector


@dataclass
class IndexingResult:
    points: list[models.PointStruct]


async def build_indexing_points(
    chunk_rows: list[dict],
    node_rows_by_id: dict,
    region_rows_by_id: dict,
    version_row: dict,
    document_row: dict,
    embedding_gateway: EmbeddingGateway,
) -> IndexingResult:
    if not chunk_rows:
        return IndexingResult(points=[])

    contextual_texts = [chunk["contextual_text"] for chunk in chunk_rows]
    cache_keys = [cache_key_for(text) for text in contextual_texts]

    async with async_session_factory() as session:
        cached = await get_cached_embeddings(session, cache_keys)

    dense_vectors: list[list[float] | None] = [cached.get(key) for key in cache_keys]
    miss_indices = [index for index, vector in enumerate(dense_vectors) if vector is None]

    if miss_indices:
        embedded = await embedding_gateway.embed_documents(
            [contextual_texts[index] for index in miss_indices]
        )
        for index, vector in zip(miss_indices, embedded, strict=True):
            dense_vectors[index] = vector

        async with async_session_factory() as session:
            await store_embeddings(
                session, [(cache_keys[index], dense_vectors[index]) for index in miss_indices]
            )

    points: list[models.PointStruct] = []
    for chunk, dense_vector in zip(chunk_rows, dense_vectors, strict=True):
        node = node_rows_by_id[chunk["source_node_id"]]
        region = region_rows_by_id[node["region_id"]]
        sparse_indices, sparse_values = build_sparse_vector(chunk["original_text"])
        payload = build_chunk_payload(chunk, node, region, version_row, document_row)
        points.append(
            models.PointStruct(
                id=str(chunk["id"]),
                vector={
                    "dense": dense_vector,
                    "sparse": models.SparseVector(indices=sparse_indices, values=sparse_values),
                },
                payload=payload,
            )
        )
    return IndexingResult(points=points)
