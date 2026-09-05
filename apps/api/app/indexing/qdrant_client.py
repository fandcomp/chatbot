"""apps/api's Qdrant touchpoints: M6's cleanup-on-delete (ADR-002's
Consequences explicitly disallow stale Qdrant points) and M7's query-time
retrieval (app/retrieval/service.py), which reuses the collection/vector
name constants below to stay in sync with the worker's qdrant_writer.py.
"""

import uuid

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings

COLLECTION_NAME = "document_chunks"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)


async def delete_document_points(organization_id: uuid.UUID, document_id: uuid.UUID) -> None:
    # organization_id is included as a second filter clause (not just
    # document_id) so this delete stays safe-by-construction per ADR-002's
    # mandatory tenant scoping, rather than relying solely on the caller
    # (delete_document's get_org_scoped_document check) to have already
    # verified ownership.
    client = get_qdrant_client()
    try:
        if not await client.collection_exists(COLLECTION_NAME):
            # Nothing has ever been indexed yet (e.g. a document deleted
            # before reaching M6) — no points, nothing to clean up.
            return
        await client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="organization_id",
                        match=models.MatchValue(value=str(organization_id)),
                    ),
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=str(document_id))
                    ),
                ]
            ),
        )
    finally:
        await client.close()
