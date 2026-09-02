# ADR-015: JWT Session via httpOnly Cookie, and Self-Service Organization Bootstrap

## Context

Milestone M1 (§52, §51, §7) requires authentication, RBAC, and tenant context, but the spec is deliberately non-prescriptive about the exact session transport (§94 lists "secure cookies/JWT" as the minimal requirement, not a specific mechanism) and does not describe a signup/provisioning flow at all. Two decisions were needed before implementation could start:

1. How is the authenticated session carried between the Next.js frontend and the FastAPI backend?
2. How do the very first `Organization` and `User` rows come to exist, given the spec has no email/invite infrastructure anywhere (`.env.example` has no SMTP/mail vars) and §87's API route list shows only `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` — no register or invite route?

## Decision

- **Session transport**: a JWT (HS256), issued on login/register, delivered exclusively via an httpOnly, `Secure` (in non-development environments), `SameSite=Lax` cookie. The browser never sees the token value directly (no `localStorage`, no client-readable cookie, no `Authorization` header path from the browser).
- **No refresh-token endpoint in v1**: the cookie has a single moderate lifetime (`JWT_EXPIRE_MINUTES`, default 720 = 12h). Expiry requires re-login rather than silent refresh. This matches the spec's own minimal route list, which has no `/auth/refresh`.
- **Tenant boundary = `organization_id`**: §50's "DATABASE CORE TABLES" list has no separate `tenants` table (only `organizations`, `users`, `organization_members`). `tenant_id` as used in ADR-009 and §7's mandatory filter language refers to `organization_id`; no redundant column is introduced.
- **Provisioning model**: `POST /auth/register` is added (beyond the spec's literal §87 list) as the sole bootstrap path — it creates a brand-new `Organization` and its first `User` as `OWNER` in a single transaction. From there, `OWNER`/`ADMIN` members create further users directly via `POST /organizations/members` (email + initial password + role, set server-side) — no email is sent. Each user gets exactly one `organization_members` row in this milestone (multi-org-per-user is not required to ship RBAC + tenant isolation and is left for future work).
- **Password hashing**: the `bcrypt` library, used directly.
- **RBAC**: a `require_role(*roles)` FastAPI dependency, layered on `get_current_user`, checked at the dependency level rather than inside individual handlers.

## Alternatives

- Bearer JWT in `localStorage` + `Authorization` header — rejected; `.claude/rules/react/security.md` explicitly forbids storing sessions in `localStorage` ("accessible to any XSS. Use httpOnly secure cookies"), and this is a standing project rule, not a per-milestone choice.
- Opaque server-side session token (session table + cookie holding only an ID) — rejected for v1; a self-contained JWT avoids a session-lookup table and matches §94's "secure cookies/JWT" language directly. Revisit if server-side revocation (e.g., force-logout-all-devices) becomes a real requirement — a JWT can't be invalidated before its own expiry without an additional denylist.
- Access + refresh token pair with a `/auth/refresh` endpoint — rejected for v1; adds meaningful complexity (refresh rotation, refresh-token storage/revocation) that the spec's own route list doesn't ask for. A 12h expiry is a reasonable v1 tradeoff.
- Email-invite flow for provisioning new users — rejected for v1; no SMTP/mail configuration exists anywhere in this repo, and building the invite/email infrastructure now would be speculative ahead of any stated requirement (YAGNI). Admin-created users with a server-set password cover the same functional need today.
- `passlib[bcrypt]` instead of `bcrypt` directly — rejected; passlib's bcrypt backend has known compatibility breakage against `bcrypt>=4.1` (it reads a `__about__.__version__` attribute bcrypt's maintainers removed), and adds an abstraction layer with no benefit here since only one hashing scheme is used.

## Reasons

- httpOnly cookies close off the single largest client-side session-theft vector (XSS reading `localStorage`) without any extra library, matching the project's own standing React security rule.
- Deriving the tenant boundary directly from `organization_id` (rather than inventing a parallel `Tenant` entity) keeps the schema aligned with §50's canonical table list and avoids a synchronization problem between two IDs that would always be equal in practice.
- A single self-service bootstrap endpoint is the minimum needed to get any organization/user into the system at all, given no seed/admin-console tooling exists yet.

## Consequences

- Cross-origin cookie delivery (frontend on `localhost:3000`, API on `localhost:8000` in dev, and likely different subdomains in production) requires `SameSite=Lax` (not `Strict`) plus CORS `allow_credentials=True` with an explicit origin allowlist (already the case in `main.py`) — `allow_credentials` can never be combined with a wildcard origin.
- No silent token refresh means a user's session simply expires after 12h of issuance; if product feedback later demands "stay signed in" beyond that, a refresh-token pair (or sliding-expiry re-issue on activity) will need its own ADR.
- Because there is no server-side session store, there is no way to forcibly invalidate an issued token before its `exp` (e.g., on password change or admin-initiated logout-all). This is an accepted gap for v1 — flagged here so it isn't mistaken for an oversight — and would require adding a denylist (e.g., Redis-backed, keyed by token `jti`) in a future milestone.
- `POST /auth/register` being open (unauthenticated) means anyone can create a new organization. This is the intended self-service model for v1; if the product later requires closed/invite-only tenant creation, this endpoint needs to be gated or removed.
- The single-org-per-user simplification means switching organizations isn't supported yet; a user who needs access to two organizations needs two separate accounts (different emails) until multi-membership is implemented.

## Status

Accepted.
