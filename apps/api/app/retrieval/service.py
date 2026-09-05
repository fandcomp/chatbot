"""RetrievalService (spec §90) — M7's orchestration of §32's pipeline up to
"Confidence Check": Legal Reference Parser -> exact structural retrieval, or
Hybrid Retrieval (dense + sparse in parallel, spec §47 rule 2) -> RRF Fusion.
Conditional reranking and everything after it is M8+.

ADR-001 (PostgreSQL as source of truth): Qdrant's document_status payload
field is baked in once, at index time (see the worker's index_document task),
and nothing re-syncs it if a version is later archived/superseded — so it is
used here only as a cheap prefilter. The final chunk list for BOTH exact and
hybrid paths is always re-fetched/re-verified live from Postgres (status,
org, knowledge_space) before being returned, and chunk text itself
(original_text) only ever lives in Postgres — Qdrant's payload never stores
it (see indexing/payload_builder.py).
"""

import asyncio
import uuid

from qdrant_client import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking.models import DocumentChunk
from app.core.config import settings
from app.documents.models import Document, DocumentLifecycleStatus, DocumentVersion
from app.indexing.qdrant_client import (
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_client,
)
from app.parsing.models import DocumentNode
from app.retrieval.embedding_gateway import QueryEmbeddingGateway
from app.retrieval.query_parser import LegalReference, parse_legal_reference
from app.retrieval.rrf import rrf_scores
from app.retrieval.schemas import RetrievalResponse, RetrievedChunk
from app.retrieval.sparse_vector import build_sparse_vector
from app.retrieval.structural_path_match import path_matches


class RetrievalService:
    def __init__(
        self,
        db: AsyncSession,
        embedding_gateway: QueryEmbeddingGateway | None = None,
    ) -> None:
        self._db = db
        self._embedding_gateway = embedding_gateway or QueryEmbeddingGateway()

    async def retrieve(
        self,
        organization_id: uuid.UUID,
        query: str,
        knowledge_space_id: uuid.UUID | None = None,
    ) -> RetrievalResponse:
        reference = parse_legal_reference(query)
        if reference is not None:
            exact_chunks = await self._exact_match(organization_id, knowledge_space_id, reference)
            if exact_chunks:
                return RetrievalResponse(query=query, mode="EXACT_STRUCTURAL", chunks=exact_chunks)

        hybrid_chunks = await self._hybrid_search(organization_id, knowledge_space_id, query)
        return RetrievalResponse(query=query, mode="HYBRID", chunks=hybrid_chunks)

    # -- Exact structural retrieval (spec §29.1, addendum §23) --------------

    async def _exact_match(
        self,
        organization_id: uuid.UUID,
        knowledge_space_id: uuid.UUID | None,
        reference: LegalReference,
    ) -> list[RetrievedChunk]:
        stmt = (
            select(DocumentChunk, DocumentNode)
            .join(DocumentNode, DocumentChunk.source_node_id == DocumentNode.id)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentVersion.status == DocumentLifecycleStatus.ACTIVE,
            )
        )
        if knowledge_space_id is not None:
            stmt = stmt.join(Document, DocumentChunk.document_id == Document.id).where(
                Document.knowledge_space_id == knowledge_space_id
            )

        if reference.kind == "ARTICLE":
            stmt = stmt.where(DocumentNode.article_number == reference.article)
            if reference.clause is not None:
                stmt = stmt.where(DocumentNode.clause_number == reference.clause)
            if reference.letter is not None:
                stmt = stmt.where(DocumentNode.letter_number == reference.letter)
            rows = (await self._db.execute(stmt)).all()
            matched_chunks = [chunk for chunk, _node in rows]
        elif reference.kind == "APPENDIX":
            stmt = stmt.where(DocumentNode.appendix_number.ilike(reference.appendix))
            rows = (await self._db.execute(stmt)).all()
            matched_chunks = [chunk for chunk, _node in rows]
        elif reference.kind == "DECISION":
            stmt = stmt.where(DocumentNode.number_normalized.ilike(reference.decision_label))
            rows = (await self._db.execute(stmt)).all()
            matched_chunks = [chunk for chunk, _node in rows]
        else:  # GENERIC_PATH
            # A node's structural_path_json can't contain N terms if its own
            # depth is shallower than N — cheap prefilter before the Python
            # subsequence check below.
            stmt = stmt.where(DocumentNode.structural_depth >= len(reference.path_terms) - 1)
            rows = (await self._db.execute(stmt)).all()
            matched_chunks = [
                chunk
                for chunk, node in rows
                if path_matches(node.structural_path_json, reference.path_terms)
            ]

        matched_chunks.sort(key=lambda chunk: chunk.sequence_number)
        return [self._chunk_to_response(chunk, score=None) for chunk in matched_chunks]

    # -- Hybrid retrieval: dense + sparse in parallel, RRF fused -------------

    async def _hybrid_search(
        self,
        organization_id: uuid.UUID,
        knowledge_space_id: uuid.UUID | None,
        query: str,
    ) -> list[RetrievedChunk]:
        dense_vector = await self._embedding_gateway.embed_query(query)
        sparse_indices, sparse_values = build_sparse_vector(query)
        query_filter = self._tenant_filter(organization_id, knowledge_space_id)

        client = get_qdrant_client()
        try:
            if not await client.collection_exists(COLLECTION_NAME):
                return []

            dense_task = client.query_points(
                collection_name=COLLECTION_NAME,
                using=DENSE_VECTOR_NAME,
                query=dense_vector,
                query_filter=query_filter,
                limit=settings.DENSE_TOP_K,
                with_payload=True,
            )
            sparse_task = client.query_points(
                collection_name=COLLECTION_NAME,
                using=SPARSE_VECTOR_NAME,
                query=models.SparseVector(indices=sparse_indices, values=sparse_values),
                query_filter=query_filter,
                limit=settings.SPARSE_TOP_K,
                with_payload=True,
            )
            dense_result, sparse_result = await asyncio.gather(dense_task, sparse_task)
        finally:
            await client.close()

        ranked_id_lists: list[list[str]] = [
            [str((point.payload or {})["chunk_id"]) for point in result.points]
            for result in (dense_result, sparse_result)
        ]

        scores = rrf_scores(ranked_id_lists)
        fused_chunk_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[
            : settings.FUSION_TOP_K
        ]
        if not fused_chunk_ids:
            return []

        return await self._fetch_verified_chunks(
            organization_id, knowledge_space_id, fused_chunk_ids, scores
        )

    async def _fetch_verified_chunks(
        self,
        organization_id: uuid.UUID,
        knowledge_space_id: uuid.UUID | None,
        chunk_ids: list[str],
        scores: dict[str, float],
    ) -> list[RetrievedChunk]:
        stmt = (
            select(DocumentChunk)
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .where(
                DocumentChunk.id.in_([uuid.UUID(chunk_id) for chunk_id in chunk_ids]),
                DocumentChunk.organization_id == organization_id,
                DocumentVersion.status == DocumentLifecycleStatus.ACTIVE,
            )
        )
        if knowledge_space_id is not None:
            stmt = stmt.join(Document, DocumentChunk.document_id == Document.id).where(
                Document.knowledge_space_id == knowledge_space_id
            )

        chunks_by_id = {
            str(chunk.id): chunk for chunk in (await self._db.execute(stmt)).scalars().all()
        }

        ordered_chunks = [chunks_by_id[cid] for cid in chunk_ids if cid in chunks_by_id]
        return [
            self._chunk_to_response(chunk, score=scores.get(str(chunk.id)))
            for chunk in ordered_chunks
        ]

    @staticmethod
    def _tenant_filter(
        organization_id: uuid.UUID, knowledge_space_id: uuid.UUID | None
    ) -> models.Filter:
        must: list[models.Condition] = [
            models.FieldCondition(
                key="organization_id", match=models.MatchValue(value=str(organization_id))
            ),
            models.FieldCondition(
                key="document_status",
                match=models.MatchValue(value=DocumentLifecycleStatus.ACTIVE.value),
            ),
        ]
        if knowledge_space_id is not None:
            must.append(
                models.FieldCondition(
                    key="knowledge_space_id",
                    match=models.MatchValue(value=str(knowledge_space_id)),
                )
            )
        return models.Filter(must=must)

    @staticmethod
    def _chunk_to_response(chunk: DocumentChunk, score: float | None) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_version_id=chunk.document_version_id,
            structural_path_text=chunk.structural_path_text,
            original_text=chunk.original_text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            sequence_number=chunk.sequence_number,
            score=score,
            parent_chunk_id=chunk.parent_chunk_id,
            token_count=chunk.token_count,
        )
