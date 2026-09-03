"""M2's `verify_upload` (SHA-256 re-verification) and M3's `parse_document`
(Docling-based generic structure parsing, chunking/embedding are M5+).
"""

import asyncio
import hashlib
from datetime import UTC, datetime

from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
)
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import bindparam, insert, select, update

from app.celery_app import celery_app
from app.database import (
    async_session_factory,
    document_nodes,
    document_regions,
    document_versions,
    processing_jobs,
)
from app.parsing.pipeline import run_pipeline
from app.storage import get_object_bytes

# ClientError codes that mean the object genuinely won't be fetchable on
# retry — anything else (throttling, transient 5xx) is treated as transient.
_PERMANENT_S3_ERROR_CODES = {"NoSuchKey", "404", "AccessDenied", "NoSuchBucket"}


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

            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="SUCCEEDED", updated_at=now)
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
