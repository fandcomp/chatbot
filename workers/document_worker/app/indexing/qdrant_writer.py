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
    "visibility": models.PayloadSchemaType.KEYWORD,
    "node_type": models.PayloadSchemaType.KEYWORD,
    "article": models.PayloadSchemaType.KEYWORD,
    "clause": models.PayloadSchemaType.KEYWORD,
    "appendix_label": models.PayloadSchemaType.KEYWORD,
}


async def ensure_collection(client: AsyncQdrantClient, dimension: int) -> None:
    if await client.collection_exists(COLLECTION_NAME):
        # ADR-021: a collection created before `visibility` existed never
        # got its index (the loop below only ever runs at collection
        # creation) and its existing points never got the payload field at
        # all (payload is baked in once, at index time — ADR-001). Both are
        # safe to run unconditionally on every call: `create_payload_index`
        # is idempotent (empirically confirmed — a duplicate call against a
        # live collection returns `completed`, not an error), and the
        # `IsEmptyCondition` filter below only ever matches points still
        # missing the field, so after the first real backfill this becomes
        # a fast empty-match no-op.
        await _ensure_visibility_backfilled(client)
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


async def _ensure_visibility_backfilled(client: AsyncQdrantClient) -> None:
    """ADR-021 self-heal for a collection that already existed before this
    field was introduced. `PUBLIC` matches the Postgres column's own
    `server_default` (`apps/api` migration `f22223eeba67`) — no document
    was ever anything other than implicitly-public before this ADR, so
    backfilling every pre-existing point to `PUBLIC` is lossless.
    """
    await client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="visibility",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    await client.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"visibility": "PUBLIC"},
        points=models.FilterSelector(
            filter=models.Filter(
                must=[models.IsEmptyCondition(is_empty=models.PayloadField(key="visibility"))]
            )
        ),
    )


async def upsert_chunks(client: AsyncQdrantClient, points: list[models.PointStruct]) -> None:
    if not points:
        return
    await client.upsert(collection_name=COLLECTION_NAME, points=points)
