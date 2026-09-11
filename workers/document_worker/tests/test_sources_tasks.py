"""Integration tests for the LAN-M1 discovery scan task against real
Postgres (docker compose). Uses LocalFakeAdapter against real temp
directories — never a real UNC share, never a provider call.
"""

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text, update

from app.database import (
    async_session_factory,
    document_versions as document_versions_table,
    engine,
    processing_jobs as processing_jobs_table,
    promotion_records,
    scan_runs,
    source_entries,
    source_roots,
)
from app.core.config import settings
from app.sources_tasks import _promote_source_entry_async, _scan_source_async


@pytest.fixture(autouse=True)
def _fast_stability_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real file-stability check (promotion.py::check_file_stable) sleeps
    # for this long between its two stats — 0 here keeps the promotion
    # tests fast without changing what they verify (the stability logic
    # itself is covered directly, with real timing, in test_promotion.py).
    monkeypatch.setattr(settings, "SCAN_STABILITY_WINDOW_SECONDS", 0)


@pytest_asyncio.fixture
async def seeded_org() -> AsyncGenerator[dict, None]:
    org_id = uuid.uuid4()
    space_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'LAN Test Org', :slug)"),
            {"id": org_id, "slug": f"lan-test-{org_id}"},
        )
        await conn.execute(
            text(
                "INSERT INTO knowledge_spaces (id, organization_id, name) "
                "VALUES (:id, :org_id, 'General')"
            ),
            {"id": space_id, "org_id": org_id},
        )
    yield {"org_id": org_id, "space_id": space_id}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM promotion_records WHERE organization_id = :oid"
            ),
            {"oid": org_id},
        )
        await conn.execute(
            text("DELETE FROM processing_jobs WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM document_versions WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM documents WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM source_entries WHERE organization_id = :oid"),
            {"oid": org_id},
        )
        await conn.execute(
            text("DELETE FROM scan_runs WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM source_roots WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM knowledge_spaces WHERE id = :id"), {"id": space_id}
        )
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})


async def _create_source(
    org_id: uuid.UUID, space_id: uuid.UUID, root_path: str, allowed_subtrees=None
) -> uuid.UUID:
    # source_type/knowledge_space_id aren't in the worker's Core Table def
    # (apps/api owns writing them at creation time, the worker only ever
    # updates health) — insert via raw SQL here to stand in for what
    # apps/api's router does.
    source_id = uuid.uuid4()
    subtrees_json = None if allowed_subtrees is None else json.dumps(list(allowed_subtrees))
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO source_roots "
                "(id, organization_id, knowledge_space_id, source_type, display_name, "
                "root_path, allowed_subtrees, health, created_at, updated_at) "
                "VALUES (:id, :org_id, :space_id, 'LOCAL_FAKE', 'test source', :root_path, "
                "CAST(:allowed_subtrees AS jsonb), 'UNKNOWN', now(), now())"
            ),
            {
                "id": source_id,
                "org_id": org_id,
                "space_id": space_id,
                "root_path": root_path,
                "allowed_subtrees": subtrees_json,
            },
        )
        await session.commit()
    return source_id


async def _create_scan_run(org_id: uuid.UUID, source_id: uuid.UUID) -> uuid.UUID:
    scan_run_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(scan_runs).values(
                id=scan_run_id,
                organization_id=org_id,
                source_root_id=source_id,
                status="RUNNING",
                entries_seen=0,
                entries_new=0,
                entries_updated=0,
            )
        )
        await session.commit()
    return scan_run_id


async def _scan_run_row(scan_run_id: uuid.UUID) -> dict:
    async with async_session_factory() as session:
        return dict(
            (await session.execute(select(scan_runs).where(scan_runs.c.id == scan_run_id)))
            .mappings()
            .one()
        )


async def _source_entries(source_id: uuid.UUID) -> list[dict]:
    async with async_session_factory() as session:
        return [
            dict(row)
            for row in (
                await session.execute(
                    select(source_entries).where(source_entries.c.source_root_id == source_id)
                )
            )
            .mappings()
            .all()
        ]


async def test_catalog_only_scan_produces_entries_and_touches_no_provider(
    seeded_org, tmp_path, monkeypatch
):
    (tmp_path / "a.pdf").write_text("fake pdf content")
    (tmp_path / "b.docx").write_text("fake docx content")

    # Catalog-only means: never even imports/calls storage or embedding
    # code. Fail loudly if this task somehow reaches for them.
    import app.storage as storage_module

    def _must_not_be_called(*_args, **_kwargs):
        raise AssertionError("discovery scan must never call object storage")

    monkeypatch.setattr(storage_module, "get_object_bytes", _must_not_be_called)

    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    scan_run_id = await _create_scan_run(org_id, source_id)

    await _scan_source_async(str(scan_run_id))

    run = await _scan_run_row(scan_run_id)
    assert run["status"] == "COMPLETED"
    entries = await _source_entries(source_id)
    assert {e["normalized_path"] for e in entries} == {"a.pdf", "b.docx"}
    assert all(e["discovery_status"] == "PRESENT" for e in entries)


async def test_offline_source_does_not_touch_existing_entries(seeded_org, tmp_path):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    unreachable_path = str(tmp_path / "does-not-exist")
    source_id = await _create_source(org_id, space_id, unreachable_path)
    scan_run_id = await _create_scan_run(org_id, source_id)

    await _scan_source_async(str(scan_run_id))

    run = await _scan_run_row(scan_run_id)
    assert run["status"] == "FAILED"
    assert await _source_entries(source_id) == []


async def test_one_inaccessible_subtree_does_not_poison_the_rest(
    seeded_org, tmp_path, monkeypatch
):
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "ok.pdf").write_text("1")
    (tmp_path / "bad").mkdir()

    import os as os_module

    real_scandir = os_module.scandir

    def fake_scandir(path):
        if str(path).endswith("bad"):
            raise PermissionError("simulated access denied")
        return real_scandir(path)

    monkeypatch.setattr(os_module, "scandir", fake_scandir)

    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    scan_run_id = await _create_scan_run(org_id, source_id)

    await _scan_source_async(str(scan_run_id))

    run = await _scan_run_row(scan_run_id)
    assert run["status"] == "PARTIAL"
    assert run["error_summary"] is not None
    assert any("bad" in e["subtree"] for e in run["error_summary"])
    entries = await _source_entries(source_id)
    assert {e["normalized_path"] for e in entries} == {"good/ok.pdf"}


async def test_rescan_with_no_changes_creates_no_new_entries(seeded_org, tmp_path):
    (tmp_path / "a.pdf").write_text("1")
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    source_id = await _create_source(org_id, space_id, str(tmp_path))

    first_scan_id = await _create_scan_run(org_id, source_id)
    await _scan_source_async(str(first_scan_id))
    assert (await _scan_run_row(first_scan_id))["entries_new"] == 1

    second_scan_id = await _create_scan_run(org_id, source_id)
    await _scan_source_async(str(second_scan_id))
    second_run = await _scan_run_row(second_scan_id)

    assert second_run["status"] == "COMPLETED"
    assert second_run["entries_new"] == 0
    entries = await _source_entries(source_id)
    assert len(entries) == 1
    assert entries[0]["last_seen_scan_id"] == second_scan_id


# ---------------------------------------------------------------------------
# LAN-M2: promote_source_entry
# ---------------------------------------------------------------------------


class _FakeTask:
    """Stands in for Celery's bound task `self` — raising the retry
    exception directly gives the test full control without depending on
    Celery's eager-mode retry semantics."""

    class _RetrySignal(Exception):
        pass

    def retry(self, exc=None, countdown=None):
        raise self._RetrySignal(str(exc))


async def _create_entry(
    org_id: uuid.UUID, source_id: uuid.UUID, normalized_path: str, content: bytes
) -> uuid.UUID:
    entry_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(source_entries).values(
                id=entry_id,
                organization_id=org_id,
                source_root_id=source_id,
                normalized_path=normalized_path,
                size_bytes=len(content),
                discovery_status="PRESENT",
                access_status="OK",
            )
        )
        await session.commit()
    return entry_id


async def _create_promotion_record(org_id: uuid.UUID, entry_id: uuid.UUID) -> uuid.UUID:
    record_id = uuid.uuid4()
    async with async_session_factory() as session:
        await session.execute(
            insert(promotion_records).values(
                id=record_id,
                organization_id=org_id,
                source_entry_id=entry_id,
                status="QUEUED",
                attempts=0,
            )
        )
        await session.commit()
    return record_id


async def _promotion_row(record_id: uuid.UUID) -> dict:
    async with async_session_factory() as session:
        return dict(
            (
                await session.execute(
                    select(promotion_records).where(promotion_records.c.id == record_id)
                )
            )
            .mappings()
            .one()
        )


def _real_pdf_bytes(marker: bytes) -> bytes:
    return b"%PDF-1.4\n%%" + marker + b"\n%%EOF"


async def test_promotion_creates_document_version_and_enqueues_verify_upload(
    seeded_org, tmp_path, monkeypatch
):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    content = _real_pdf_bytes(b"stable-file")
    (tmp_path / "policy.pdf").write_bytes(content)
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    entry_id = await _create_entry(org_id, source_id, "policy.pdf", content)
    record_id = await _create_promotion_record(org_id, entry_id)

    enqueued = []
    from app.tasks import verify_upload as verify_upload_task

    monkeypatch.setattr(
        verify_upload_task, "delay", lambda job_id: enqueued.append(job_id)
    )

    await _promote_source_entry_async(_FakeTask(), str(record_id))

    record = await _promotion_row(record_id)
    assert record["status"] == "COMPLETED"
    assert record["document_version_id"] is not None
    assert len(enqueued) == 1

    async with async_session_factory() as session:
        version = (
            await session.execute(
                select(document_versions_table).where(
                    document_versions_table.c.id == record["document_version_id"]
                )
            )
        ).mappings().one()
        job = (
            await session.execute(
                select(processing_jobs_table).where(
                    processing_jobs_table.c.document_version_id == version["id"]
                )
            )
        ).mappings().one()
    assert version["status"] == "UPLOADED"
    assert version["source_entry_id"] == entry_id
    assert str(job["id"]) == enqueued[0]


async def test_duplicate_content_links_to_existing_version_without_new_storage_write(
    seeded_org, tmp_path, monkeypatch
):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    content = _real_pdf_bytes(b"duplicate-content")
    (tmp_path / "original.pdf").write_bytes(content)
    (tmp_path / "copy.pdf").write_bytes(content)
    source_id = await _create_source(org_id, space_id, str(tmp_path))

    import app.sources_tasks as sources_tasks_module
    from app.tasks import verify_upload as verify_upload_task

    monkeypatch.setattr(verify_upload_task, "delay", lambda job_id: None)
    put_calls = []
    monkeypatch.setattr(
        sources_tasks_module,
        "put_object_stream",
        lambda key, fileobj, content_type: put_calls.append(key),
    )

    entry_a = await _create_entry(org_id, source_id, "original.pdf", content)
    record_a = await _create_promotion_record(org_id, entry_a)
    await _promote_source_entry_async(_FakeTask(), str(record_a))
    assert (await _promotion_row(record_a))["status"] == "COMPLETED"
    assert len(put_calls) == 1

    entry_b = await _create_entry(org_id, source_id, "copy.pdf", content)
    record_b = await _create_promotion_record(org_id, entry_b)
    await _promote_source_entry_async(_FakeTask(), str(record_b))

    record_b_row = await _promotion_row(record_b)
    assert record_b_row["status"] == "DUPLICATE_LINKED"
    assert record_b_row["document_version_id"] == (await _promotion_row(record_a))[
        "document_version_id"
    ]
    # No second storage write for the duplicate.
    assert len(put_calls) == 1


async def test_unsupported_extension_fails_without_staging(seeded_org, tmp_path):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    (tmp_path / "legacy.doc").write_bytes(b"old word doc bytes")
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    entry_id = await _create_entry(org_id, source_id, "legacy.doc", b"old word doc bytes")
    record_id = await _create_promotion_record(org_id, entry_id)

    await _promote_source_entry_async(_FakeTask(), str(record_id))

    record = await _promotion_row(record_id)
    assert record["status"] == "FAILED"
    assert "Unsupported file type" in record["error_message"]


async def test_disk_watermark_pauses_rather_than_fails(seeded_org, tmp_path, monkeypatch):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    content = _real_pdf_bytes(b"disk-watermark")
    (tmp_path / "a.pdf").write_bytes(content)
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    entry_id = await _create_entry(org_id, source_id, "a.pdf", content)
    record_id = await _create_promotion_record(org_id, entry_id)

    import app.sources_tasks as sources_tasks_module

    def _fake_check_disk_watermark(staging_dir, min_free_mb):
        from app.sources.promotion import DiskWatermarkError

        raise DiskWatermarkError("simulated low disk")

    monkeypatch.setattr(
        sources_tasks_module, "check_disk_watermark", _fake_check_disk_watermark
    )

    with pytest.raises(_FakeTask._RetrySignal):
        await _promote_source_entry_async(_FakeTask(), str(record_id))

    record = await _promotion_row(record_id)
    assert record["status"] == "PAUSED_CAPACITY"


async def test_stale_lease_is_reclaimed_by_a_later_attempt(seeded_org, tmp_path, monkeypatch):
    org_id, space_id = seeded_org["org_id"], seeded_org["space_id"]
    content = _real_pdf_bytes(b"stale-lease")
    (tmp_path / "a.pdf").write_bytes(content)
    source_id = await _create_source(org_id, space_id, str(tmp_path))
    entry_id = await _create_entry(org_id, source_id, "a.pdf", content)
    record_id = await _create_promotion_record(org_id, entry_id)

    # Simulate a worker that crashed mid-promotion: a lease that already
    # expired, held by a different (fake) worker.
    async with async_session_factory() as session:
        await session.execute(
            update(promotion_records)
            .where(promotion_records.c.id == record_id)
            .values(
                lease_owner=uuid.uuid4(),
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=5),
                status="STAGING",
            )
        )
        await session.commit()

    from app.tasks import verify_upload as verify_upload_task

    monkeypatch.setattr(verify_upload_task, "delay", lambda job_id: None)

    await _promote_source_entry_async(_FakeTask(), str(record_id))

    record = await _promotion_row(record_id)
    assert record["status"] == "COMPLETED"
    assert record["attempts"] == 1
