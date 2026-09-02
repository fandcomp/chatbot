"""The one real M2 task: verify an uploaded object's integrity.

Scope is deliberately narrow — SHA-256 re-verification only. Docling parsing,
structure detection, chunking, and embedding are M3+ (see docs/
MASTER_DEVELOPMENT_SPEC.md §59's flow diagram and the M2 plan's scope note).
"""

import asyncio
import hashlib
from datetime import UTC, datetime

from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
)
from sqlalchemy import select, update

from app.celery_app import celery_app
from app.database import async_session_factory, document_versions, processing_jobs
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
            await session.execute(
                update(processing_jobs)
                .where(processing_jobs.c.id == job_id)
                .values(status="SUCCEEDED", updated_at=datetime.now(UTC))
            )
            # Version intentionally stays PROCESSING — reaching PARSED requires
            # M3's real parsing, which this task does not do.
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
