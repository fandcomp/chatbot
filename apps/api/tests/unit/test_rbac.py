"""RBAC enforcement tests: OWNER can manage members, VIEWER cannot.

Requires `docker compose up -d` to be running from the repo root (real Postgres).
"""

from collections.abc import Callable

from httpx import AsyncClient

OWNER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
}
NEW_MEMBER_PAYLOAD = {
    "email": "viewer@acme-regulatory.io",
    "password": "supersecret123",
    "full_name": "Vera Viewer",
    "role": "VIEWER",
}


async def test_owner_can_create_a_member_with_any_role(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=OWNER_PAYLOAD)

    # Act
    response = await client.post("/organizations/members", json=NEW_MEMBER_PAYLOAD)

    # Assert
    assert response.status_code == 201
    assert response.json()["role"] == "VIEWER"


async def test_viewer_cannot_create_a_member(client_factory: Callable[[], AsyncClient]) -> None:
    # Arrange: owner registers and creates a VIEWER member
    owner_client = client_factory()
    await owner_client.post("/auth/register", json=OWNER_PAYLOAD)
    await owner_client.post("/organizations/members", json=NEW_MEMBER_PAYLOAD)

    # Log in as the VIEWER in a separate session
    viewer_client = client_factory()
    await viewer_client.post(
        "/auth/login",
        json={
            "email": NEW_MEMBER_PAYLOAD["email"],
            "password": NEW_MEMBER_PAYLOAD["password"],
        },
    )

    # Act
    response = await viewer_client.post(
        "/organizations/members",
        json={
            "email": "another@acme-regulatory.io",
            "password": "supersecret123",
            "role": "EDITOR",
        },
    )

    # Assert
    assert response.status_code == 403


async def test_owner_can_change_a_members_role(client: AsyncClient) -> None:
    await client.post("/auth/register", json=OWNER_PAYLOAD)
    create_response = await client.post("/organizations/members", json=NEW_MEMBER_PAYLOAD)
    member_id = create_response.json()["id"]

    response = await client.patch(f"/organizations/members/{member_id}", json={"role": "EDITOR"})

    assert response.status_code == 200
    assert response.json()["role"] == "EDITOR"


async def test_owner_can_remove_a_member(client: AsyncClient) -> None:
    await client.post("/auth/register", json=OWNER_PAYLOAD)
    create_response = await client.post("/organizations/members", json=NEW_MEMBER_PAYLOAD)
    member_id = create_response.json()["id"]

    response = await client.delete(f"/organizations/members/{member_id}")
    assert response.status_code == 204

    list_response = await client.get("/organizations/members")
    assert all(member["id"] != member_id for member in list_response.json())


async def test_viewer_cannot_change_a_members_role(client_factory: Callable[[], AsyncClient]) -> None:
    owner_client = client_factory()
    await owner_client.post("/auth/register", json=OWNER_PAYLOAD)
    create_response = await owner_client.post("/organizations/members", json=NEW_MEMBER_PAYLOAD)
    member_id = create_response.json()["id"]

    viewer_client = client_factory()
    await viewer_client.post(
        "/auth/login",
        json={"email": NEW_MEMBER_PAYLOAD["email"], "password": NEW_MEMBER_PAYLOAD["password"]},
    )

    response = await viewer_client.patch(
        f"/organizations/members/{member_id}", json={"role": "ADMIN"}
    )
    assert response.status_code == 403


async def test_cannot_demote_the_organizations_last_owner(client: AsyncClient) -> None:
    register_response = await client.post("/auth/register", json=OWNER_PAYLOAD)
    members = (await client.get("/organizations/members")).json()
    owner_member_id = members[0]["id"]
    assert register_response.status_code == 201

    response = await client.patch(
        f"/organizations/members/{owner_member_id}", json={"role": "ADMIN"}
    )
    assert response.status_code == 409


async def test_cannot_remove_the_organizations_last_owner(client: AsyncClient) -> None:
    await client.post("/auth/register", json=OWNER_PAYLOAD)
    members = (await client.get("/organizations/members")).json()
    owner_member_id = members[0]["id"]

    response = await client.delete(f"/organizations/members/{owner_member_id}")
    assert response.status_code == 409


async def test_can_demote_an_owner_when_another_owner_remains(client: AsyncClient) -> None:
    await client.post("/auth/register", json=OWNER_PAYLOAD)
    members = (await client.get("/organizations/members")).json()
    first_owner_id = members[0]["id"]

    second_owner_response = await client.post(
        "/organizations/members",
        json={
            "email": "second-owner@acme-regulatory.io",
            "password": "supersecret123",
            "role": "OWNER",
        },
    )
    assert second_owner_response.status_code == 201

    response = await client.patch(
        f"/organizations/members/{first_owner_id}", json={"role": "ADMIN"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"
