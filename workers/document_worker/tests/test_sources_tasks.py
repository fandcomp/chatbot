"""Integration tests for the LAN-M1 discovery scan task against real
Postgres (docker compose). Uses LocalFakeAdapter against real temp
directories — never a real UNC share, never a provider call.
"""

import json
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import insert, select, text

from app.database import async_session_factory, engine, scan_runs, source_entries, source_roots
from app.sources_tasks import _scan_source_async


@pytest_asyncio.fixture
async def seeded_org() -> AsyncGenerator[dict, None]:
    org_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'LAN Test Org', :slug)"),
            {"id": org_id, "slug": f"lan-test-{org_id}"},
        )
    yield {"org_id": org_id}
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "DELETE FROM source_entries WHERE organization_id = :oid"
            ),
            {"oid": org_id},
        )
        await conn.execute(
            text("DELETE FROM scan_runs WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(
            text("DELETE FROM source_roots WHERE organization_id = :oid"), {"oid": org_id}
        )
        await conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": org_id})


async def _create_source(org_id: uuid.UUID, root_path: str, allowed_subtrees=None) -> uuid.UUID:
    # source_type isn't in the worker's Core Table def (apps/api owns
    # writing it at creation time, the worker only ever updates health) —
    # insert via raw SQL here to stand in for what apps/api's router does.
    source_id = uuid.uuid4()
    subtrees_json = None if allowed_subtrees is None else json.dumps(list(allowed_subtrees))
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO source_roots "
                "(id, organization_id, source_type, display_name, root_path, "
                "allowed_subtrees, health, created_at, updated_at) "
                "VALUES (:id, :org_id, 'LOCAL_FAKE', 'test source', :root_path, "
                "CAST(:allowed_subtrees AS jsonb), 'UNKNOWN', now(), now())"
            ),
            {
                "id": source_id,
                "org_id": org_id,
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

    org_id = seeded_org["org_id"]
    source_id = await _create_source(org_id, str(tmp_path))
    scan_run_id = await _create_scan_run(org_id, source_id)

    await _scan_source_async(str(scan_run_id))

    run = await _scan_run_row(scan_run_id)
    assert run["status"] == "COMPLETED"
    entries = await _source_entries(source_id)
    assert {e["normalized_path"] for e in entries} == {"a.pdf", "b.docx"}
    assert all(e["discovery_status"] == "PRESENT" for e in entries)


async def test_offline_source_does_not_touch_existing_entries(seeded_org, tmp_path):
    org_id = seeded_org["org_id"]
    unreachable_path = str(tmp_path / "does-not-exist")
    source_id = await _create_source(org_id, unreachable_path)
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

    org_id = seeded_org["org_id"]
    source_id = await _create_source(org_id, str(tmp_path))
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
    org_id = seeded_org["org_id"]
    source_id = await _create_source(org_id, str(tmp_path))

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
