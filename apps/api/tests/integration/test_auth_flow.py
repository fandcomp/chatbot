"""Integration tests for register/login/me/logout against real Postgres.

Requires `docker compose up -d` to be running from the repo root.
"""

from httpx import AsyncClient

REGISTER_PAYLOAD = {
    "organization_name": "Acme Regulatory",
    "email": "owner@acme-regulatory.io",
    "password": "supersecret123",
    "full_name": "Ada Owner",
}


async def test_register_creates_org_and_owner_and_sets_session_cookie(
    client: AsyncClient,
) -> None:
    # Act
    response = await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert body["role"] == "OWNER"
    assert "session" in response.cookies


async def test_register_with_duplicate_email_returns_409(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.post(
        "/auth/register",
        json={**REGISTER_PAYLOAD, "organization_name": "Another Org"},
    )

    # Assert
    assert response.status_code == 409


async def test_login_with_correct_credentials_returns_session(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.post(
        "/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )

    # Assert
    assert response.status_code == 200
    assert "session" in response.cookies


async def test_login_with_wrong_password_returns_generic_401(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    response = await client.post(
        "/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": "wrong-password"},
    )

    # Assert
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_login_with_unknown_email_returns_same_generic_401(client: AsyncClient) -> None:
    # Act
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@unknown-domain.io", "password": "whatever123"},
    )

    # Assert
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_me_returns_current_user_after_register(client: AsyncClient) -> None:
    # Arrange
    register_response = await client.post("/auth/register", json=REGISTER_PAYLOAD)
    organization_id = register_response.json()["organization_id"]

    # Act
    response = await client.get("/auth/me")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert body["organization_id"] == organization_id
    assert body["role"] == "OWNER"


async def test_me_without_session_returns_401(client: AsyncClient) -> None:
    # Act
    response = await client.get("/auth/me")

    # Assert
    assert response.status_code == 401


async def test_logout_clears_session_so_subsequent_me_is_401(client: AsyncClient) -> None:
    # Arrange
    await client.post("/auth/register", json=REGISTER_PAYLOAD)

    # Act
    logout_response = await client.post("/auth/logout")
    me_response = await client.get("/auth/me")

    # Assert
    assert logout_response.status_code == 204
    assert me_response.status_code == 401
