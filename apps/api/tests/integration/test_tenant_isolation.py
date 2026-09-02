"""Mandatory tenant-isolation test per ADR-009 / spec §97: a user from one
organization must never be able to see another organization's data.

Requires `docker compose up -d` to be running from the repo root.
"""

from collections.abc import Callable

from httpx import AsyncClient

ORG_A_PAYLOAD = {
    "organization_name": "Org A",
    "email": "owner-a@org-a-corp.io",
    "password": "supersecret123",
}
ORG_B_PAYLOAD = {
    "organization_name": "Org B",
    "email": "owner-b@org-b-corp.io",
    "password": "supersecret123",
}


async def test_org_member_list_never_leaks_another_organizations_members(
    client_factory: Callable[[], AsyncClient],
) -> None:
    # Arrange: two independent sessions, one per organization
    client_a = client_factory()
    client_b = client_factory()

    register_a = await client_a.post("/auth/register", json=ORG_A_PAYLOAD)
    register_b = await client_b.post("/auth/register", json=ORG_B_PAYLOAD)
    org_a_id = register_a.json()["organization_id"]
    org_b_id = register_b.json()["organization_id"]
    assert org_a_id != org_b_id

    # Act
    members_seen_by_a = await client_a.get("/organizations/members")
    members_seen_by_b = await client_b.get("/organizations/members")

    # Assert
    a_emails = {member["email"] for member in members_seen_by_a.json()}
    b_emails = {member["email"] for member in members_seen_by_b.json()}

    assert a_emails == {ORG_A_PAYLOAD["email"]}
    assert b_emails == {ORG_B_PAYLOAD["email"]}
    assert ORG_B_PAYLOAD["email"] not in a_emails
    assert ORG_A_PAYLOAD["email"] not in b_emails
