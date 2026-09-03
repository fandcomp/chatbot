import hashlib
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select, text

from app.core.config import settings
from app.database import async_session_factory, document_versions, processing_jobs
from app.storage import _client
from app.tasks import _verify_upload_async

_PDF_BYTES = b"%PDF-1.4\n%test minimal pdf content for hashing\n%%EOF"


def _put_test_object(key: str, content: bytes) -> None:
    _client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content)


async def _seed_version_and_job(seeded: dict, file_hash: str, storage_path: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO document_versions (id, organization_id, document_id, "
                "version_number, file_hash, original_filename, mime_type, size_bytes, "
                "storage_path, status) VALUES (:id, :org_id, :doc_id, 1, :hash, "
                "'test.pdf', 'application/pdf', :size, :path, 'UPLOADED')"
            ),
            {
                "id": seeded["version_id"],
                "org_id": seeded["org_id"],
                "doc_id": seeded["document_id"],
                "hash": file_hash,
                "size": len(_PDF_BYTES),
                "path": storage_path,
            },
        )
        await session.execute(
            insert(processing_jobs).values(
                id=seeded["job_id"],
                organization_id=seeded["org_id"],
                document_version_id=seeded["version_id"],
                status="QUEUED",
                attempts=0,
            )
        )
        await session.commit()


async def _job_row(job_id) -> dict:
    async with async_session_factory() as session:
        return dict(
            (
                await session.execute(
                    select(processing_jobs).where(processing_jobs.c.id == job_id)
                )
            )
            .mappings()
            .one()
        )


async def _version_row(version_id) -> dict:
    async with async_session_factory() as session:
        return dict(
            (
                await session.execute(
                    select(document_versions).where(document_versions.c.id == version_id)
                )
            )
            .mappings()
            .one()
        )


@pytest.mark.asyncio
async def test_verify_upload_chains_into_parse_document_when_hash_matches(seeded_document_version):
    seeded = seeded_document_version
    storage_path = (
        f"organization/{seeded['org_id']}/documents/{seeded['document_id']}/"
        f"versions/{seeded['version_id']}/original/test.pdf"
    )
    _put_test_object(storage_path, _PDF_BYTES)
    file_hash = hashlib.sha256(_PDF_BYTES).hexdigest()
    await _seed_version_and_job(seeded, file_hash, storage_path)

    with patch("app.tasks.parse_document.delay") as mock_delay:
        await _verify_upload_async(str(seeded["job_id"]), attempts=1)

    mock_delay.assert_called_once_with(str(seeded["job_id"]))
    row = await _job_row(seeded["job_id"])
    # The job represents "this version's current async work" end to end —
    # it stays PROCESSING (not SUCCEEDED) until M3's parse_document resolves it.
    assert row["status"] == "PROCESSING"
    version = await _version_row(seeded["version_id"])
    assert version["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_verify_upload_marks_job_failed_when_hash_mismatches(seeded_document_version):
    seeded = seeded_document_version
    storage_path = (
        f"organization/{seeded['org_id']}/documents/{seeded['document_id']}/"
        f"versions/{seeded['version_id']}/original/test.pdf"
    )
    _put_test_object(storage_path, _PDF_BYTES)
    wrong_hash = "0" * 64
    await _seed_version_and_job(seeded, wrong_hash, storage_path)

    await _verify_upload_async(str(seeded["job_id"]), attempts=1)

    row = await _job_row(seeded["job_id"])
    assert row["status"] == "FAILED"
    assert row["error_message"] is not None
    version = await _version_row(seeded["version_id"])
    assert version["status"] == "PROCESSING_FAILED"
