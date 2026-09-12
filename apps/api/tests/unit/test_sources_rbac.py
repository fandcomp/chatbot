"""RBAC and tenant-isolation checks for the LAN-M1 sources admin API
(spec: docs/LAN_ARCHIVE_IMPLEMENTATION_PLAN.md LAN-M1 acceptance criterion
#7 — every new endpoint tenant-scoped and role-gated from day one).
"""

import pytest
from httpx import AsyncClient

from app.sources import router as sources_router

REGISTER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
}
OTHER_ORG_PAYLOAD = {
    "organization_name": "Other Org",
    "email": "owner@other-org.io",
    "password": "supersecret123",
}


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources_router, "enqueue_scan_source", lambda scan_run_id: "fake-task-id")


async def _create_member(owner_client: AsyncClient, email: str, role: str) -> None:
    await owner_client.post(
        "/organizations/members",
        json={"email": email, "password": "supersecret123", "role": role},
    )


async def _create_source(client: AsyncClient) -> str:
    space_id = (await client.get("/knowledge-spaces")).json()[0]["id"]
    response = await client.post(
        "/sources",
        json={
            "source_type": "LOCAL_FAKE",
            "knowledge_space_id": space_id,
            "display_name": "Test LAN Source",
            "root_path": "/tmp/does-not-matter-for-this-test",
        },
    )
    return response.json()["id"]


async def test_owner_can_create_and_list_a_source(client_factory) -> None:
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]

    create_response = await owner.post(
        "/sources",
        json={
            "source_type": "LOCAL_FAKE",
            "knowledge_space_id": space_id,
            "display_name": "Archive Share",
            "root_path": "/mnt/archive",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["display_name"] == "Archive Share"
    assert create_response.json()["health"] == "UNKNOWN"

    list_response = await owner.get("/sources")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_editor_cannot_create_a_source(client_factory) -> None:
    owner, editor = client_factory(), client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    await _create_member(owner, "editor@acme-regulatory.io", "EDITOR")
    await editor.post(
        "/auth/login", json={"email": "editor@acme-regulatory.io", "password": "supersecret123"}
    )
    space_id = (await owner.get("/knowledge-spaces")).json()[0]["id"]

    response = await editor.post(
        "/sources",
        json={
            "source_type": "LOCAL_FAKE",
            "knowledge_space_id": space_id,
            "display_name": "x",
            "root_path": "/tmp/x",
        },
    )

    assert response.status_code == 403


async def test_viewer_can_list_but_not_trigger_a_scan(client_factory) -> None:
    owner, viewer = client_factory(), client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)
    await _create_member(owner, "viewer@acme-regulatory.io", "VIEWER")
    await viewer.post(
        "/auth/login", json={"email": "viewer@acme-regulatory.io", "password": "supersecret123"}
    )

    list_response = await viewer.get("/sources")
    assert list_response.status_code == 200

    scan_response = await viewer.post(f"/sources/{source_id}/scan")
    assert scan_response.status_code == 403


async def test_owner_can_trigger_a_scan_and_it_enqueues_the_worker_task(client_factory) -> None:
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)

    response = await owner.post(f"/sources/{source_id}/scan")

    assert response.status_code == 201
    assert response.json()["status"] == "RUNNING"

    scan_runs_response = await owner.get(f"/sources/{source_id}/scan-runs")
    assert scan_runs_response.status_code == 200
    assert len(scan_runs_response.json()) == 1


async def test_cannot_access_another_organizations_source(client_factory) -> None:
    owner_a, owner_b = client_factory(), client_factory()
    await owner_a.post("/auth/register", json=REGISTER_PAYLOAD)
    await owner_b.post("/auth/register", json=OTHER_ORG_PAYLOAD)
    source_id = await _create_source(owner_a)

    scan_response = await owner_b.post(f"/sources/{source_id}/scan")
    scan_runs_response = await owner_b.get(f"/sources/{source_id}/scan-runs")
    entries_response = await owner_b.get(f"/sources/{source_id}/entries")

    assert scan_response.status_code == 404
    assert scan_runs_response.status_code == 404
    assert entries_response.status_code == 404


async def test_listing_entries_of_a_freshly_created_source_is_empty(client_factory) -> None:
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)

    response = await owner.get(f"/sources/{source_id}/entries")

    assert response.status_code == 200
    assert response.json() == []


async def test_a_new_source_is_enabled_by_default(client_factory) -> None:
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)

    response = await owner.get("/sources")

    assert response.json()[0]["id"] == source_id
    assert response.json()[0]["is_enabled"] is True


async def test_disabling_a_source_blocks_new_scans_and_promotions(client_factory) -> None:
    # Arrange — a misconfigured source with a promotable catalog entry.
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)

    # Act
    disable_response = await owner.post(f"/sources/{source_id}/disable")

    # Assert
    assert disable_response.status_code == 200
    assert disable_response.json()["is_enabled"] is False

    scan_response = await owner.post(f"/sources/{source_id}/scan")
    assert scan_response.status_code == 409

    promote_response = await owner.post(
        f"/sources/{source_id}/entries/promote",
        json={"source_entry_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert promote_response.status_code == 409


async def test_re_enabling_a_source_allows_scans_again(client_factory) -> None:
    owner = client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)
    await owner.post(f"/sources/{source_id}/disable")

    enable_response = await owner.post(f"/sources/{source_id}/enable")
    assert enable_response.status_code == 200
    assert enable_response.json()["is_enabled"] is True

    scan_response = await owner.post(f"/sources/{source_id}/scan")
    assert scan_response.status_code == 201


async def test_editor_cannot_disable_a_source(client_factory) -> None:
    owner, editor = client_factory(), client_factory()
    await owner.post("/auth/register", json=REGISTER_PAYLOAD)
    source_id = await _create_source(owner)
    await _create_member(owner, "editor@acme-regulatory.io", "EDITOR")
    await editor.post(
        "/auth/login", json={"email": "editor@acme-regulatory.io", "password": "supersecret123"}
    )

    response = await editor.post(f"/sources/{source_id}/disable")

    assert response.status_code == 403


async def test_cannot_disable_another_organizations_source(client_factory) -> None:
    owner_a, owner_b = client_factory(), client_factory()
    await owner_a.post("/auth/register", json=REGISTER_PAYLOAD)
    await owner_b.post("/auth/register", json=OTHER_ORG_PAYLOAD)
    source_id = await _create_source(owner_a)

    response = await owner_b.post(f"/sources/{source_id}/disable")

    assert response.status_code == 404
