"""Pure-logic checks for ADR-021's visibility policy — no DB/HTTP needed.
"""

import uuid

from app.documents.models import DocumentVisibility
from app.documents.visibility_policy import (
    ALLOWED_VISIBILITIES,
    allowed_visibilities_for,
)
from app.organizations.models import OrgRole
from app.retrieval.service import RetrievalService


def test_every_org_role_has_a_non_empty_allowed_visibility_set() -> None:
    for role in OrgRole:
        allowed = allowed_visibilities_for(role)
        assert isinstance(allowed, frozenset)
        assert len(allowed) > 0
        assert allowed <= frozenset(DocumentVisibility)


def test_viewer_is_restricted_to_public_only() -> None:
    assert ALLOWED_VISIBILITIES[OrgRole.VIEWER] == frozenset({DocumentVisibility.PUBLIC})


def test_editor_cannot_see_restricted() -> None:
    assert DocumentVisibility.RESTRICTED not in ALLOWED_VISIBILITIES[OrgRole.EDITOR]
    assert DocumentVisibility.PUBLIC in ALLOWED_VISIBILITIES[OrgRole.EDITOR]
    assert DocumentVisibility.INTERNAL in ALLOWED_VISIBILITIES[OrgRole.EDITOR]


def test_admin_and_owner_see_every_level() -> None:
    for role in (OrgRole.ADMIN, OrgRole.OWNER):
        assert ALLOWED_VISIBILITIES[role] == frozenset(DocumentVisibility)


def test_tenant_filter_includes_a_visibility_match_any_condition() -> None:
    # ADR-021: the Qdrant prefilter must never omit the visibility clause —
    # this is the enforcement point the anti-pattern in spec §53 forbids
    # skipping (filter-before-fetch, not post-hoc).
    allowed = frozenset({DocumentVisibility.PUBLIC, DocumentVisibility.INTERNAL})
    query_filter = RetrievalService._tenant_filter(uuid.uuid4(), None, allowed)

    visibility_conditions = [
        condition
        for condition in query_filter.must
        if getattr(condition, "key", None) == "visibility"
    ]
    assert len(visibility_conditions) == 1
    matched_values = set(visibility_conditions[0].match.any)
    assert matched_values == {"PUBLIC", "INTERNAL"}
