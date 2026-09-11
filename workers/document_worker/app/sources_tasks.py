"""LAN-M1 discovery scan task (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md
§3, ADR-020). Kept in its own module rather than growing the already-large
`tasks.py` (coding-style: many small files over few large ones).

Catalog-only: never calls Docling, an embedding gateway, an LLM gateway, or
`put_object` — this task only ever reads filesystem metadata and writes to
`source_entries`/`scan_runs`.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update

from app.celery_app import celery_app
from app.core.config import settings
from app.database import (
    async_session_factory,
    document_versions,
    documents,
    processing_jobs,
    promotion_records,
    scan_runs,
    source_entries,
    source_roots,
)
from app.sources.adapter import EntryAccessStatus
from app.sources.discovery import run_one_page
from app.sources.local_fake_adapter import LocalFakeAdapter
from app.sources.promotion import (
    ALLOWED_EXTENSIONS,
    DiskWatermarkError,
    FileTooLargeError,
    FileUnstableError,
    check_disk_watermark,
    check_file_stable,
    extension_for_path,
    mime_type_for_extension,
    sanitize_filename,
    stage_to_temp_file,
)
from app.sources.windows_unc_adapter import WindowsUNCAdapter
from app.storage import build_original_object_key, put_object_stream

# Deliberately NOT imported at module level: app.tasks imports
# app.celery_app, which imports this module (to register its tasks) — a
# module-level `from app.tasks import verify_upload` here creates a real
# circular import whenever app.tasks happens to be the first of the two
# modules Python starts loading (e.g. a test importing from app.tasks
# directly). Importing lazily, inside the function that actually calls it,
# sidesteps the cycle since by call time both modules have finished loading.

_MAX_PAGES_PER_TASK_INVOCATION = 200
"""Safety bound, not a design limit: re-enqueues itself if a scan is still
running after this many pages in one Celery task execution, so a single
task never monopolizes a worker slot indefinitely on a very large source."""


def _build_adapter(source_type: str, root_path: str):
    if source_type == "LOCAL_FAKE":
        return LocalFakeAdapter(root_path)
    if source_type == "WINDOWS_UNC":
        return WindowsUNCAdapter(root_path)
    raise ValueError(f"unknown source_type: {source_type!r}")


async def _load_scan_context(scan_run_id: uuid.UUID) -> dict:
    async with async_session_factory() as session:
        scan_run_row = (
            await session.execute(select(scan_runs).where(scan_runs.c.id == scan_run_id))
        ).mappings().one()
        source_row = (
            await session.execute(
                select(source_roots).where(source_roots.c.id == scan_run_row["source_root_id"])
            )
        ).mappings().one()
        return {"scan_run": dict(scan_run_row), "source": dict(source_row)}


async def _persist_health(source_id: uuid.UUID, healthy: bool) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(source_roots)
            .where(source_roots.c.id == source_id)
            .values(
                health="HEALTHY" if healthy else "UNREACHABLE",
                health_checked_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _persist_page(
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
    scan_run_id: uuid.UUID,
    result,
) -> tuple[int, int]:
    """Upserts SourceEntry rows for one page and returns (new_count,
    updated_count). Runs in its own transaction so each page is a durable
    checkpoint — a crash after this commit resumes from the next page, not
    from the beginning of the scan."""
    new_count = 0
    updated_count = 0
    async with async_session_factory() as session:
        for entry in result.entries:
            existing = (
                await session.execute(
                    select(source_entries.c.id).where(
                        source_entries.c.source_root_id == source_id,
                        source_entries.c.normalized_path == entry.normalized_path,
                    )
                )
            ).scalar_one_or_none()
            now = datetime.now(UTC)
            if existing is None:
                await session.execute(
                    insert(source_entries).values(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        source_root_id=source_id,
                        normalized_path=entry.normalized_path,
                        size_bytes=entry.size_bytes,
                        mtime=entry.mtime,
                        last_seen_scan_id=scan_run_id,
                        discovery_status="PRESENT",
                        access_status=entry.access_status.value,
                        created_at=now,
                        updated_at=now,
                    )
                )
                new_count += 1
            else:
                await session.execute(
                    update(source_entries)
                    .where(source_entries.c.id == existing)
                    .values(
                        size_bytes=entry.size_bytes,
                        mtime=entry.mtime,
                        last_seen_scan_id=scan_run_id,
                        discovery_status="PRESENT",
                        access_status=entry.access_status.value,
                        updated_at=now,
                    )
                )
                updated_count += 1

        error_dicts = [
            {"subtree": e.subtree, "error_type": e.error_type.value, "message": e.message}
            for e in result.errors
        ]
        scan_run_row = (
            await session.execute(select(scan_runs).where(scan_runs.c.id == scan_run_id))
        ).mappings().one()
        merged_errors = list(scan_run_row["error_summary"] or []) + error_dicts

        await session.execute(
            update(scan_runs)
            .where(scan_runs.c.id == scan_run_id)
            .values(
                cursor=result.next_cursor,
                entries_seen=scan_run_row["entries_seen"] + len(result.entries),
                entries_new=scan_run_row["entries_new"] + new_count,
                entries_updated=scan_run_row["entries_updated"] + updated_count,
                error_summary=merged_errors or None,
            )
        )
        await session.commit()
    return new_count, updated_count


async def _finalize_scan(scan_run_id: uuid.UUID, status: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(scan_runs)
            .where(scan_runs.c.id == scan_run_id)
            .values(status=status, finished_at=datetime.now(UTC))
        )
        await session.commit()


async def _scan_source_async(scan_run_id_str: str) -> None:
    scan_run_id = uuid.UUID(scan_run_id_str)
    context = await _load_scan_context(scan_run_id)
    source = context["source"]
    scan_run = context["scan_run"]

    adapter = _build_adapter(source["source_type"], source["root_path"])

    health = adapter.check_health()
    await _persist_health(source["id"], health.healthy)
    if not health.healthy:
        # Source offline/unreachable: never mark existing entries as
        # missing on this basis (addendum §3.1) — just record the failure
        # and stop. Existing SourceEntry rows are left untouched.
        await _finalize_scan(scan_run_id, "FAILED")
        return

    subtrees = source["allowed_subtrees"] or [""]
    cursor = scan_run["cursor"]
    had_errors = bool(scan_run["error_summary"])

    for _ in range(_MAX_PAGES_PER_TASK_INVOCATION):
        result = run_one_page(adapter, subtrees, cursor, settings.SCAN_PAGE_SIZE)
        await _persist_page(source["organization_id"], source["id"], scan_run_id, result)
        had_errors = had_errors or bool(result.errors)
        cursor = result.next_cursor
        if result.done:
            await _finalize_scan(scan_run_id, "PARTIAL" if had_errors else "COMPLETED")
            return

    # Safety bound hit — re-enqueue to continue from the last committed
    # checkpoint rather than blocking this worker slot indefinitely.
    scan_source.delay(scan_run_id_str)


@celery_app.task(
    bind=True,
    name="document_worker.scan_source",
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def scan_source(self, scan_run_id: str) -> None:
    asyncio.run(_scan_source_async(scan_run_id))


# ---------------------------------------------------------------------------
# LAN-M2: promote_source_entry
# ---------------------------------------------------------------------------


async def _claim_lease(promotion_record_id: uuid.UUID, lease_seconds: int) -> dict | None:
    """Atomic claim: a crashed worker's lease is simply reclaimed once it
    expires — no separate lock service (see PromotionRecord's own
    docstring). Returns None if another worker currently holds the lease or
    this record is already in a terminal state (idempotent no-op)."""
    lease_owner = uuid.uuid4()
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        result = await session.execute(
            update(promotion_records)
            .where(
                promotion_records.c.id == promotion_record_id,
                promotion_records.c.status.notin_(["COMPLETED", "DUPLICATE_LINKED"]),
                (promotion_records.c.lease_expires_at.is_(None))
                | (promotion_records.c.lease_expires_at < now),
            )
            .values(
                lease_owner=lease_owner,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempts=promotion_records.c.attempts + 1,
            )
            .returning(promotion_records.c.id)
        )
        claimed = result.scalar_one_or_none()
        await session.commit()
        if claimed is None:
            return None
        row = (
            await session.execute(
                select(promotion_records).where(promotion_records.c.id == promotion_record_id)
            )
        ).mappings().one()
        return dict(row)


async def _set_promotion_status(
    promotion_record_id: uuid.UUID, status: str, error_message: str | None = None
) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(promotion_records)
            .where(promotion_records.c.id == promotion_record_id)
            .values(status=status, error_message=error_message)
        )
        await session.commit()


async def _find_duplicate_version(organization_id: uuid.UUID, file_hash: str) -> dict | None:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                select(document_versions.c.id, document_versions.c.document_id).where(
                    document_versions.c.organization_id == organization_id,
                    document_versions.c.file_hash == file_hash,
                )
            )
        ).mappings().first()
        return dict(row) if row else None


async def _link_duplicate(
    promotion_record_id: uuid.UUID, document_id: uuid.UUID, document_version_id: uuid.UUID
) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(promotion_records)
            .where(promotion_records.c.id == promotion_record_id)
            .values(
                status="DUPLICATE_LINKED",
                document_id=document_id,
                document_version_id=document_version_id,
                error_message=None,
            )
        )
        await session.commit()


async def _create_document_and_version(
    organization_id: uuid.UUID,
    knowledge_space_id: uuid.UUID,
    source_entry_id: uuid.UUID,
    sanitized_filename: str,
    mime_type: str,
    size_bytes: int,
    file_hash: str,
) -> dict:
    """Creates a brand-new Document (version 1) — LAN-M2 does not attempt
    to reconcile a promoted file against an existing document by title/
    path; that is a later-milestone incremental-sync refinement, not this
    one's scope."""
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(documents).values(
                id=document_id,
                organization_id=organization_id,
                title=sanitized_filename,
                knowledge_space_id=knowledge_space_id,
            )
        )
        storage_key = build_original_object_key(
            organization_id, document_id, version_id, sanitized_filename
        )
        await session.execute(
            insert(document_versions).values(
                id=version_id,
                organization_id=organization_id,
                document_id=document_id,
                version_number=1,
                file_hash=file_hash,
                original_filename=sanitized_filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
                source_entry_id=source_entry_id,
                storage_path=storage_key,
                status="UPLOADED",
            )
        )
        await session.execute(
            insert(processing_jobs).values(
                id=job_id,
                organization_id=organization_id,
                document_version_id=version_id,
                status="QUEUED",
                attempts=0,
            )
        )
        await session.execute(
            update(promotion_records)
            .where(promotion_records.c.source_entry_id == source_entry_id)
            .values(
                status="COMPLETED",
                document_id=document_id,
                document_version_id=version_id,
                error_message=None,
            )
        )
        await session.commit()
    return {
        "document_id": document_id,
        "version_id": version_id,
        "job_id": job_id,
        "storage_key": storage_key,
    }


async def _promote_source_entry_async(self, promotion_record_id_str: str) -> None:
    from app.tasks import verify_upload  # see module-level comment on why this is lazy

    promotion_record_id = uuid.UUID(promotion_record_id_str)

    record = await _claim_lease(promotion_record_id, settings.PROMOTION_LEASE_SECONDS)
    if record is None:
        # Already completed/duplicate-linked, or another worker holds the
        # lease right now — safe, idempotent no-op either way.
        return

    async with async_session_factory() as session:
        entry_row = (
            await session.execute(
                select(source_entries).where(source_entries.c.id == record["source_entry_id"])
            )
        ).mappings().one()
        source_row = (
            await session.execute(
                select(source_roots).where(source_roots.c.id == entry_row["source_root_id"])
            )
        ).mappings().one()

    normalized_path = entry_row["normalized_path"]
    extension = extension_for_path(normalized_path)
    if extension not in ALLOWED_EXTENSIONS:
        await _set_promotion_status(
            promotion_record_id,
            "FAILED",
            f"Unsupported file type {extension!r} — only PDF/DOCX are supported "
            "until LAN-M3 adds DOC/legacy parsing.",
        )
        return

    try:
        check_disk_watermark(settings.STAGING_DIR, settings.MIN_FREE_DISK_MB)
    except DiskWatermarkError as exc:
        await _set_promotion_status(promotion_record_id, "PAUSED_CAPACITY", str(exc))
        self.retry(exc=exc, countdown=60)

    adapter = _build_adapter(source_row["source_type"], source_row["root_path"])

    await _set_promotion_status(promotion_record_id, "STABILITY_WAIT")
    try:
        check_file_stable(adapter, normalized_path, settings.SCAN_STABILITY_WINDOW_SECONDS)
    except (FileUnstableError, FileNotFoundError) as exc:
        await _set_promotion_status(promotion_record_id, "STABILITY_WAIT", str(exc))
        self.retry(exc=exc, countdown=30)

    await _set_promotion_status(promotion_record_id, "STAGING")
    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    try:
        staged = stage_to_temp_file(adapter, normalized_path, settings.STAGING_DIR, max_size_bytes)
    except FileTooLargeError as exc:
        await _set_promotion_status(promotion_record_id, "FAILED", str(exc))
        return

    try:
        # Re-verify after transfer — a file that changed mid-copy must
        # never become a published version (addendum §6).
        post_stat = adapter.stat(normalized_path)
        pre_stat_matches = (
            post_stat.exists
            and post_stat.size_bytes == staged.size_bytes
        )
        if not pre_stat_matches:
            raise FileUnstableError(normalized_path)

        duplicate = await _find_duplicate_version(source_row["organization_id"], staged.sha256_hex)
        if duplicate is not None:
            await _link_duplicate(
                promotion_record_id, duplicate["document_id"], duplicate["id"]
            )
            return

        sanitized_filename = sanitize_filename(normalized_path)
        mime_type = mime_type_for_extension(extension)
        created = await _create_document_and_version(
            organization_id=source_row["organization_id"],
            knowledge_space_id=source_row["knowledge_space_id"],
            source_entry_id=entry_row["id"],
            sanitized_filename=sanitized_filename,
            mime_type=mime_type,
            size_bytes=staged.size_bytes,
            file_hash=staged.sha256_hex,
        )
        with open(staged.temp_path, "rb") as fileobj:
            put_object_stream(created["storage_key"], fileobj, mime_type)
        verify_upload.delay(str(created["job_id"]))
    except FileUnstableError as exc:
        await _set_promotion_status(promotion_record_id, "STABILITY_WAIT", str(exc))
        self.retry(exc=exc, countdown=30)
    finally:
        if os.path.exists(staged.temp_path):
            os.remove(staged.temp_path)


@celery_app.task(
    bind=True,
    name="document_worker.promote_source_entry",
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def promote_source_entry(self, promotion_record_id: str) -> None:
    asyncio.run(_promote_source_entry_async(self, promotion_record_id))
