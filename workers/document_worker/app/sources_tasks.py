"""LAN-M1 discovery scan task (docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md
§3, ADR-020). Kept in its own module rather than growing the already-large
`tasks.py` (coding-style: many small files over few large ones).

Catalog-only: never calls Docling, an embedding gateway, an LLM gateway, or
`put_object` — this task only ever reads filesystem metadata and writes to
`source_entries`/`scan_runs`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import insert, select, update

from app.celery_app import celery_app
from app.core.config import settings
from app.database import async_session_factory, scan_runs, source_entries, source_roots
from app.sources.adapter import EntryAccessStatus
from app.sources.discovery import run_one_page
from app.sources.local_fake_adapter import LocalFakeAdapter
from app.sources.windows_unc_adapter import WindowsUNCAdapter

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
