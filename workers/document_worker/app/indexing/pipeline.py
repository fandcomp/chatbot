"""Orchestrates M6: embed each version's chunks (dense), build sparse
vectors and payloads, and produce Qdrant points ready to upsert. Never
re-chunks — reads M5's already-persisted `document_chunks` rows as-is.
"""

from dataclasses import dataclass

from qdrant_client import models

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

    dense_vectors = await embedding_gateway.embed_documents(
        [chunk["contextual_text"] for chunk in chunk_rows]
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
