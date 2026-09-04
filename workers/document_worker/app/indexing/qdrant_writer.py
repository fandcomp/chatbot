"""ADR-002's single shared Qdrant collection: one collection for every
tenant, isolated only via payload filtering (mandatory `organization_id`
filter on every read — ADR-009) — never per-tenant collections.

Collection creation is idempotent and lazy (checked/created here, inside the
indexing task itself) — this stack has no dedicated Qdrant schema-migration
tool.
"""

from qdrant_client import AsyncQdrantClient, models

COLLECTION_NAME = "document_chunks"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

_PAYLOAD_INDEX_FIELDS: dict[str, models.PayloadSchemaType] = {
    "organization_id": models.PayloadSchemaType.UUID,
    "knowledge_space_id": models.PayloadSchemaType.UUID,
    "document_id": models.PayloadSchemaType.UUID,
    "document_version_id": models.PayloadSchemaType.UUID,
    "document_status": models.PayloadSchemaType.KEYWORD,
    "node_type": models.PayloadSchemaType.KEYWORD,
    "article": models.PayloadSchemaType.KEYWORD,
    "clause": models.PayloadSchemaType.KEYWORD,
    "appendix_label": models.PayloadSchemaType.KEYWORD,
}


async def ensure_collection(client: AsyncQdrantClient, dimension: int) -> None:
    if await client.collection_exists(COLLECTION_NAME):
        return
    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF),
        },
    )
    for field_name, field_schema in _PAYLOAD_INDEX_FIELDS.items():
        await client.create_payload_index(
            collection_name=COLLECTION_NAME, field_name=field_name, field_schema=field_schema
        )


async def upsert_chunks(client: AsyncQdrantClient, points: list[models.PointStruct]) -> None:
    if not points:
        return
    await client.upsert(collection_name=COLLECTION_NAME, points=points)
