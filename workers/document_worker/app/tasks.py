"""M2's `verify_upload` (SHA-256 re-verification), M3's `parse_document`
(Docling-based generic structure parsing), M4's `interpret_structure`
(specialized interpretation), M5's `chunk_document` (hierarchical chunking),
and M6's `index_document` (Voyage embedding + Qdrant/sparse indexing).
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime

import voyageai.error as voyage_errors
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
)
from celery.exceptions import SoftTimeLimitExceeded
from qdrant_client import AsyncQdrantClient
from sqlalchemy import bindparam, insert, select, update

from app.celery_app import celery_app
from app.chunking.pipeline import build_document_chunks
from app.core.config import settings
from app.database import (
    async_session_factory,
    document_chunks,
    document_nodes,
    document_regions,
    document_relations,
    document_structure_profiles,
    document_versions,
    documents,
    processing_jobs,
)
from app.indexing.embedding_gateway import EmbeddingGateway
from app.indexing.pipeline import build_indexing_points
from app.indexing.qdrant_writer import ensure_collection, upsert_chunks
from app.interpretation.pipeline import interpret_document
from app.parsing.pipeline import run_pipeline
from app.storage import get_object_bytes

# ClientError codes that mean the object genuinely won't be fetchable on
# retry — anything else (throttling, transient 5xx) is treated as transient.
_PERMANENT_S3_ERROR_CODES = {"NoSuchKey", "404", "AccessDenied", "NoSuchBucket"}

# Voyage errors that resolve on their own (rate limits, transient network/5xx)
# — these must reach Celery's autoretry_for, not resolve the job to FAILED on
# the first hit. Auth/malformed-request errors never resolve on retry, so
# they fall through to the generic except below.
_TRANSIENT_VOYAGE_ERRORS = (
    voyage_errors.RateLimitError,
    voyage_errors.ServiceUnavailableError,
    voyage_errors.APIConnectionError,
    voyage_errors.Timeout,
    voyage_errors.TryAgain,
)


async def _verify_upload_async(job_id: str, attempts: int) -> None:
    async with async_session_factory() as session:
        job_row = (
            await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id))
        ).mappings().one()

        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="PROCESSING", attempts=attempts, updated_at=datetime.now(UTC))
        )
        await session.execute(
            update(document_versions)
            .where(document_versions.c.id == job_row["document_version_id"])
            .values(status="PROCESSING", updated_at=datetime.now(UTC))
        )
        await session.commit()

        version_row = (
            await session.execute(
                select(document_versions).where(
                    document_versions.c.id == job_row["document_version_id"]
                )
            )
        ).mappings().one()

        try:
            content = get_object_bytes(version_row["storage_path"])
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in _PERMANENT_S3_ERROR_CODES:
                # Not a "the object doesn't exist" case — e.g. throttling or a
                # transient 5xx from MinIO/S3. Re-raise so Celery's
                # autoretry_for (§60: retry transient object-storage errors)
                # handles it instead of failing the job outright.
                raise
            # NoSuchKey/AccessDenied etc. won't resolve on retry — permanent.
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(
                    status="FAILED",
                    error_message=f"Object fetch failed: {exc}",
                    updated_at=datetime.now(UTC),
                )
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == job_row["document_version_id"])
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
            await session.commit()
            return

        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash == version_row["file_hash"]:
            # Chain into M3's real parsing under the same job — no new job
            # row, no frontend polling changes needed. The job stays
            # PROCESSING (not SUCCEEDED) until parse_document resolves it.
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="PROCESSING", updated_at=datetime.now(UTC))
            )
            await session.commit()
            parse_document.delay(job_id)
            return
        else:
            # Hash mismatch is permanent (corruption/tampering) — no retry.
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(
                    status="FAILED",
                    error_message="SHA-256 verification failed: stored object does not match "
                    "the hash recorded at upload time.",
                    updated_at=datetime.now(UTC),
                )
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == job_row["document_version_id"])
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
        await session.commit()


@celery_app.task(
    bind=True,
    name="document_worker.verify_upload",
    autoretry_for=(
        EndpointConnectionError,
        ConnectionClosedError,
        TimeoutError,
        OSError,
        ClientError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def verify_upload(self, job_id: str) -> None:
    asyncio.run(_verify_upload_async(job_id, attempts=self.request.retries + 1))


def _node_row(node, organization_id, document_version_id, now) -> dict:
    return {
        "id": node.id,
        "organization_id": organization_id,
        "document_version_id": document_version_id,
        "region_id": node.region_id,
        "parent_id": node.parent_id,
        "previous_id": node.previous_id,
        "node_type": node.node_type,
        "label": node.label,
        "title": node.title,
        "number_raw": node.number_raw,
        "number_normalized": node.number_normalized,
        "numbering_style": node.numbering_style,
        "text": node.text,
        "normalized_text": node.normalized_text,
        "depth": node.depth,
        "sequence_number": node.sequence_number,
        # A GroupItem-derived node with no covered descendants at all (rare —
        # an empty list/section group) would otherwise violate the NOT NULL
        # page_start/page_end columns; fall back to page 1 rather than fail
        # the whole document over a single decorative empty container.
        "page_start": node.page_start if node.page_start is not None else 1,
        "page_end": node.page_end if node.page_end is not None else 1,
        "bounding_box": node.bounding_box,
        "confidence": node.confidence,
        "source_provenance": node.source_provenance,
        "structural_path_json": node.structural_path_json,
        "structural_depth": node.structural_depth,
        "created_at": now,
        "updated_at": now,
    }


async def _parse_document_async(job_id: str, attempts: int) -> None:
    async with async_session_factory() as session:
        job_row = (
            await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id))
        ).mappings().one()
        organization_id = job_row["organization_id"]
        version_id = job_row["document_version_id"]

        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="PROCESSING", attempts=attempts, updated_at=datetime.now(UTC))
        )
        await session.commit()

        version_row = (
            await session.execute(
                select(document_versions).where(document_versions.c.id == version_id)
            )
        ).mappings().one()

        async def _fail(message: str) -> None:
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="FAILED", error_message=message, updated_at=datetime.now(UTC))
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
            await session.commit()

        try:
            content = get_object_bytes(version_row["storage_path"])
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in _PERMANENT_S3_ERROR_CODES:
                raise
            await _fail(f"Object fetch failed: {exc}")
            return

        try:
            result = run_pipeline(content, version_row["original_filename"])
        except SoftTimeLimitExceeded:
            # An adversarial or pathologically complex PDF (any authenticated
            # tenant can upload arbitrary content, up to the size cap) could
            # otherwise tie up a worker indefinitely at Level 3's forced OCR.
            # Not retried — the same document would just time out again.
            await _fail(
                "Parsing exceeded the time limit — the document may be too large or complex."
            )
            return
        except Exception as exc:  # noqa: BLE001 - Docling can raise a wide variety of
            # parser errors for a malformed PDF; addendum §14 says never fail
            # a document just for an empty text layer, but a conversion that
            # raises outright (corrupt file) is a genuine, permanent failure.
            await _fail(f"Parsing failed: {exc}")
            return

        if result.status == "PROCESSING_FAILED":
            await _fail("Parsing produced no content — the document may be corrupt or empty.")
            return

        now = datetime.now(UTC)
        try:
            if result.regions:
                await session.execute(
                    insert(document_regions),
                    [
                        {
                            "id": region.id,
                            "organization_id": organization_id,
                            "document_version_id": version_id,
                            "region_type": region.region_type,
                            "page_start": region.page_start,
                            "page_end": region.page_end,
                            "sequence_number": region.sequence_number,
                            "confidence": region.confidence,
                            "created_at": now,
                            "updated_at": now,
                        }
                        for region in result.regions
                    ],
                )
            if result.nodes:
                await session.execute(
                    insert(document_nodes),
                    [_node_row(node, organization_id, version_id, now) for node in result.nodes],
                )
                next_id_updates = [
                    {"node_id": node.id, "next_id": node.next_id}
                    for node in result.nodes
                    if node.next_id is not None
                ]
                if next_id_updates:
                    await session.execute(
                        update(document_nodes)
                        .where(document_nodes.c.id == bindparam("node_id"))
                        .values(next_id=bindparam("next_id")),
                        next_id_updates,
                    )

            # Job stays PROCESSING (not SUCCEEDED) — chained into
            # interpret_structure under the same job row below, same pattern
            # verify_upload -> parse_document already established.
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="PROCESSING", updated_at=now)
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status=result.status, updated_at=now)
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - a persistence failure (e.g. a
            # StringDataRightTruncation from an oversized extracted title) must
            # never leave the job stuck at PROCESSING forever with no error.
            await session.rollback()
            await _fail(f"Persisting parsed structure failed: {exc}")
            return

    interpret_structure.delay(job_id)


@celery_app.task(
    bind=True,
    name="document_worker.parse_document",
    autoretry_for=(
        EndpointConnectionError,
        ConnectionClosedError,
        TimeoutError,
        OSError,
        ClientError,
    ),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    # Bounds Docling's cascade against a pathological/adversarial upload —
    # content is fully attacker-controlled up to the existing size cap.
    # NOTE: Celery only enforces time limits under the prefork pool (via
    # SIGALRM); the `--pool=solo` this repo's README requires for local
    # Windows dev does NOT enforce these — they take effect in a prefork-pool
    # production deployment.
    soft_time_limit=300,
    time_limit=360,
)
def parse_document(self, job_id: str) -> None:
    asyncio.run(_parse_document_async(job_id, attempts=self.request.retries + 1))


def _node_update_row(node, now: datetime) -> dict:
    return {
        "node_id": node.id,
        "node_type": node.node_type,
        "semantic_role": node.semantic_role,
        "label": node.label,
        "structural_path_json": node.structural_path_json,
        "structural_path_text": node.structural_path_text,
        "structural_depth": node.structural_depth,
        "chapter_number": node.chapter_number,
        "article_number": node.article_number,
        "clause_number": node.clause_number,
        "letter_number": node.letter_number,
        "appendix_number": node.appendix_number,
        "confidence": node.confidence,
        "updated_at": now,
    }


async def _interpret_structure_async(job_id: str, attempts: int) -> None:
    async with async_session_factory() as session:
        job_row = (
            await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id))
        ).mappings().one()
        organization_id = job_row["organization_id"]
        version_id = job_row["document_version_id"]

        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="PROCESSING", attempts=attempts, updated_at=datetime.now(UTC))
        )
        await session.commit()

        version_row = (
            await session.execute(
                select(document_versions).where(document_versions.c.id == version_id)
            )
        ).mappings().one()

        async def _fail(message: str) -> None:
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="FAILED", error_message=message, updated_at=datetime.now(UTC))
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
            await session.commit()

        region_rows = (
            await session.execute(
                select(document_regions).where(
                    document_regions.c.document_version_id == version_id
                )
            )
        ).mappings().all()
        node_rows = (
            await session.execute(
                select(document_nodes).where(document_nodes.c.document_version_id == version_id)
            )
        ).mappings().all()

        try:
            result = interpret_document(
                [dict(row) for row in node_rows], [dict(row) for row in region_rows]
            )
        except Exception as exc:  # noqa: BLE001 - a malformed/unexpected node
            # shape must resolve the job to FAILED, not strand it at
            # PROCESSING forever.
            await _fail(f"Structure interpretation failed: {exc}")
            return

        # M3's own OCR-fallback REVIEW_REQUIRED must never be silently
        # upgraded by M4's structural confidence — the text itself is
        # already suspect regardless of how confidently it was re-typed.
        if version_row["status"] == "REVIEW_REQUIRED":
            final_status = "REVIEW_REQUIRED"
        elif result.aggregate_confidence >= settings.STRUCTURE_HIGH_CONFIDENCE:
            final_status = "APPROVED"
        else:
            final_status = "REVIEW_REQUIRED"

        now = datetime.now(UTC)
        # M2-M4's job is already terminal (SUCCEEDED) by the time a version
        # lands here — chunking needs its OWN new job row rather than
        # regressing a terminal job back to PROCESSING (that would break the
        # frontend's "stop polling once terminal" invariant). Only set once
        # persistence below actually succeeds; reset to None on failure so a
        # rolled-back row is never enqueued.
        chunk_job_id: uuid.UUID | None = None
        try:
            node_updates = [_node_update_row(node, now) for node in result.nodes]
            if node_updates:
                await session.execute(
                    update(document_nodes)
                    .where(document_nodes.c.id == bindparam("node_id"))
                    .values(
                        node_type=bindparam("node_type"),
                        semantic_role=bindparam("semantic_role"),
                        label=bindparam("label"),
                        structural_path_json=bindparam("structural_path_json"),
                        structural_path_text=bindparam("structural_path_text"),
                        structural_depth=bindparam("structural_depth"),
                        chapter_number=bindparam("chapter_number"),
                        article_number=bindparam("article_number"),
                        clause_number=bindparam("clause_number"),
                        letter_number=bindparam("letter_number"),
                        appendix_number=bindparam("appendix_number"),
                        confidence=bindparam("confidence"),
                        updated_at=bindparam("updated_at"),
                    ),
                    node_updates,
                )

            await session.execute(
                insert(document_structure_profiles).values(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    document_version_id=version_id,
                    created_at=now,
                    updated_at=now,
                    **result.profile,
                )
            )

            if final_status == "APPROVED":
                chunk_job_id = uuid.uuid4()
                await session.execute(
                    insert(processing_jobs).values(
                        id=chunk_job_id,
                        organization_id=organization_id,
                        document_version_id=version_id,
                        status="QUEUED",
                        attempts=0,
                    )
                )

            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="SUCCEEDED", updated_at=now)
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status=final_status, updated_at=now)
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - a persistence failure here
            # must never leave the job stuck at PROCESSING forever either.
            await session.rollback()
            chunk_job_id = None
            await _fail(f"Persisting structural interpretation failed: {exc}")

    if chunk_job_id is not None:
        chunk_document.delay(str(chunk_job_id))


@celery_app.task(
    bind=True,
    name="document_worker.interpret_structure",
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def interpret_structure(self, job_id: str) -> None:
    asyncio.run(_interpret_structure_async(job_id, attempts=self.request.retries + 1))


def _chunk_row(chunk, organization_id, document_id, document_version_id, now) -> dict:
    return {
        "id": chunk.id,
        "organization_id": organization_id,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "source_node_id": chunk.source_node_id,
        "parent_chunk_id": chunk.parent_chunk_id,
        "previous_chunk_id": chunk.previous_chunk_id,
        # next_chunk_id is a forward self-reference (like M3's NodeSpec.next_id)
        # — set via a bulk UPDATE after every row exists, not here.
        "depth": chunk.depth,
        "sequence_number": chunk.sequence_number,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "original_text": chunk.original_text,
        "contextual_text": chunk.contextual_text,
        "semantic_summary": None,
        "token_count": chunk.token_count,
        "structural_path_text": chunk.structural_path_text,
        "created_at": now,
        "updated_at": now,
    }


async def _chunk_document_async(job_id: str, attempts: int) -> None:
    async with async_session_factory() as session:
        job_row = (
            await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id))
        ).mappings().one()
        organization_id = job_row["organization_id"]
        version_id = job_row["document_version_id"]

        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="PROCESSING", attempts=attempts, updated_at=datetime.now(UTC))
        )
        await session.execute(
            update(document_versions)
            .where(document_versions.c.id == version_id)
            .values(status="INDEXING", updated_at=datetime.now(UTC))
        )
        await session.commit()

        version_row = (
            await session.execute(
                select(document_versions).where(document_versions.c.id == version_id)
            )
        ).mappings().one()
        document_id = version_row["document_id"]

        document_row = (
            await session.execute(select(documents).where(documents.c.id == document_id))
        ).mappings().one()
        document_title = document_row["title"]

        async def _fail(message: str) -> None:
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="FAILED", error_message=message, updated_at=datetime.now(UTC))
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
            await session.commit()

        node_rows = (
            await session.execute(
                select(document_nodes).where(document_nodes.c.document_version_id == version_id)
            )
        ).mappings().all()

        try:
            result = build_document_chunks([dict(row) for row in node_rows], document_title)
        except Exception as exc:  # noqa: BLE001 - a malformed/unexpected node
            # shape must resolve the job to FAILED, not strand it at
            # PROCESSING forever.
            await _fail(f"Chunking failed: {exc}")
            return

        now = datetime.now(UTC)
        try:
            if result.chunks:
                await session.execute(
                    insert(document_chunks),
                    [
                        _chunk_row(chunk, organization_id, document_id, version_id, now)
                        for chunk in result.chunks
                    ],
                )
                next_chunk_updates = [
                    {"chunk_id": chunk.id, "next_chunk_id": chunk.next_chunk_id}
                    for chunk in result.chunks
                    if chunk.next_chunk_id is not None
                ]
                if next_chunk_updates:
                    await session.execute(
                        update(document_chunks)
                        .where(document_chunks.c.id == bindparam("chunk_id"))
                        .values(next_chunk_id=bindparam("next_chunk_id")),
                        next_chunk_updates,
                    )

            # Job stays PROCESSING (not SUCCEEDED) — chained into
            # index_document under the same job row below. Unlike M4->M5,
            # there is no human-approval gate between chunking and indexing,
            # so this mirrors M2->M3->M4's single-job-chain pattern instead.
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="PROCESSING", updated_at=now)
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - a persistence failure here
            # must never leave the job stuck at PROCESSING forever either.
            await session.rollback()
            await _fail(f"Persisting chunks failed: {exc}")
            return

    index_document.delay(job_id)


@celery_app.task(
    bind=True,
    name="document_worker.chunk_document",
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def chunk_document(self, job_id: str) -> None:
    asyncio.run(_chunk_document_async(job_id, attempts=self.request.retries + 1))


async def _index_document_async(job_id: str, attempts: int) -> None:
    async with async_session_factory() as session:
        job_row = (
            await session.execute(select(processing_jobs).where(processing_jobs.c.id == job_id))
        ).mappings().one()
        version_id = job_row["document_version_id"]

        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="PROCESSING", attempts=attempts, updated_at=datetime.now(UTC))
        )
        await session.commit()

        version_row = (
            await session.execute(
                select(document_versions).where(document_versions.c.id == version_id)
            )
        ).mappings().one()
        document_row = (
            await session.execute(
                select(documents).where(documents.c.id == version_row["document_id"])
            )
        ).mappings().one()

        async def _fail(message: str) -> None:
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="FAILED", error_message=message, updated_at=datetime.now(UTC))
            )
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == version_id)
                .values(status="PROCESSING_FAILED", updated_at=datetime.now(UTC))
            )
            await session.commit()

        chunk_rows = (
            await session.execute(
                select(document_chunks).where(document_chunks.c.document_version_id == version_id)
            )
        ).mappings().all()
        node_rows = (
            await session.execute(
                select(document_nodes).where(document_nodes.c.document_version_id == version_id)
            )
        ).mappings().all()
        region_rows = (
            await session.execute(
                select(document_regions).where(
                    document_regions.c.document_version_id == version_id
                )
            )
        ).mappings().all()

        node_rows_by_id = {row["id"]: dict(row) for row in node_rows}
        region_rows_by_id = {row["id"]: dict(row) for row in region_rows}

        # A point is only ever upserted on the path that goes on to set the
        # version ACTIVE below — bake that into the payload's document_status
        # now rather than the version's current (still "INDEXING") DB value,
        # or every point would carry a permanently stale status that M7's
        # mandatory document_status=ACTIVE retrieval filter would never match.
        active_version_row = {**dict(version_row), "status": "ACTIVE"}

        try:
            result = await build_indexing_points(
                [dict(row) for row in chunk_rows],
                node_rows_by_id,
                region_rows_by_id,
                active_version_row,
                dict(document_row),
                EmbeddingGateway(),
            )
        except _TRANSIENT_VOYAGE_ERRORS:
            # Rate limit / transient network / 5xx — let Celery's
            # autoretry_for retry with backoff instead of failing the job
            # outright (the job stays at "PROCESSING", set above).
            raise
        except Exception as exc:  # noqa: BLE001 - a Voyage API error (bad
            # request, malformed response) must resolve the job to FAILED,
            # not strand it at PROCESSING forever.
            await _fail(f"Embedding failed: {exc}")
            return

        client = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        try:
            await ensure_collection(client, settings.VOYAGE_EMBEDDING_DIMENSION)
            await upsert_chunks(client, result.points)
        except Exception as exc:  # noqa: BLE001 - a Qdrant write failure must
            # resolve the job to FAILED, not strand it at PROCESSING forever.
            await _fail(f"Indexing failed: {exc}")
            return
        finally:
            await client.close()

        now = datetime.now(UTC)
        await session.execute(
            update(processing_jobs)
            .where(processing_jobs.c.id == job_id)
            .values(status="SUCCEEDED", updated_at=now)
        )
        await session.execute(
            update(document_versions)
            .where(document_versions.c.id == version_id)
            .values(status="ACTIVE", updated_at=now)
        )

        # M13: auto-supersede — this document's previous ACTIVE version (if
        # any) is no longer the current regulation now that this one is live.
        # Correctness holds without touching Qdrant: M7's retrieval already
        # re-verifies status live against Postgres on every query (that
        # version's stale Qdrant points, if any, are excluded there).
        superseded_version_ids = (
            await session.execute(
                select(document_versions.c.id).where(
                    document_versions.c.document_id == version_row["document_id"],
                    document_versions.c.id != version_id,
                    document_versions.c.status == "ACTIVE",
                )
            )
        ).scalars().all()
        for old_version_id in superseded_version_ids:
            await session.execute(
                update(document_versions)
                .where(document_versions.c.id == old_version_id)
                .values(status="SUPERSEDED", updated_at=now)
            )
            await session.execute(
                insert(document_relations).values(
                    id=uuid.uuid4(),
                    organization_id=version_row["organization_id"],
                    from_document_version_id=old_version_id,
                    to_document_version_id=version_id,
                    relation_type="SUPERSEDED_BY",
                    created_at=now,
                )
            )

        await session.commit()


@celery_app.task(
    bind=True,
    name="document_worker.index_document",
    autoretry_for=(OSError, TimeoutError, *_TRANSIENT_VOYAGE_ERRORS),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def index_document(self, job_id: str) -> None:
    asyncio.run(_index_document_async(job_id, attempts=self.request.retries + 1))
