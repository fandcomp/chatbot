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
