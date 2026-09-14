from app.documents.models import DocumentVisibility
from app.organizations.models import OrgRole

# ADR-021 — role-based static mapping (spec §7/§53's `USER_ALLOWED_
# VISIBILITY`, never itself defined by the spec). No per-document grant
# list exists yet (explicitly deferred, see the ADR's Alternatives
# section) — a role's set here is the ceiling on what it may ever see.
ALLOWED_VISIBILITIES: dict[OrgRole, frozenset[DocumentVisibility]] = {
    OrgRole.VIEWER: frozenset({DocumentVisibility.PUBLIC}),
    OrgRole.EDITOR: frozenset({DocumentVisibility.PUBLIC, DocumentVisibility.INTERNAL}),
    OrgRole.ADMIN: frozenset(DocumentVisibility),
    OrgRole.OWNER: frozenset(DocumentVisibility),
}


def allowed_visibilities_for(role: OrgRole) -> frozenset[DocumentVisibility]:
    return ALLOWED_VISIBILITIES[role]
