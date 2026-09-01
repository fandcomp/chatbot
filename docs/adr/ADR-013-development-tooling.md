# ADR-013: Development Tooling — pnpm + uv + Infra-Only Docker Compose

## Context

The spec names the storage/runtime technologies (§4: PostgreSQL, Qdrant, Redis, S3/MinIO, Next.js, FastAPI) but does not mandate a specific JavaScript package manager, Python package manager, or how local development processes relate to Docker Compose. This decision was needed to actually stand up Milestone M0 (§98) and is **not** a spec mandate — it is a pragmatic engineering choice, recorded here per §100's "ADR wajib untuk keputusan besar" so the reasoning stays traceable.

## Decision

- **JavaScript/TypeScript monorepo**: `pnpm` workspaces (`pnpm-workspace.yaml` covering `apps/*` and `packages/*`).
- **Python**: `uv` for dependency management and virtual environments in `apps/api`.
- **Docker Compose scope**: infrastructure only — Postgres, Redis, Qdrant, MinIO (`docker-compose.yml` at repo root). Next.js and FastAPI run as local dev processes (`pnpm --filter web dev`, `uv run uvicorn app.main:app --reload` / `fastapi dev`), not as Docker services in development.

## Alternatives

- npm or yarn instead of pnpm — rejected; pnpm's content-addressable store and native workspace support are a better fit for a multi-app monorepo (`apps/web`, future `packages/*`) with meaningfully less disk usage and faster installs than npm/yarn workspaces.
- Poetry instead of uv — rejected; uv's speed (Rust-based resolver/installer) and single-binary distribution reduce setup friction, and its lockfile-based resolution matches pnpm's determinism story on the JS side.
- Containerizing `apps/web`/`apps/api` in Docker Compose for local dev — rejected; slower hot-reload/iteration loop than running the dev servers natively, and the spec's own M0 target list (§98) already separates "Docker Compose" from "Next.js"/"FastAPI" as distinct line items, implying infra-only compose was the intended reading.

## Reasons

- Keeps local dev iteration fast (native file-watching for Next.js/FastAPI hot reload) while still giving every developer identical, disposable infra via Compose.
- Both pnpm and uv are widely adopted, actively maintained, and align with this environment's existing ECC stack-detection mappings (`typescript`/`nextjs`/`react` → pnpm-compatible commands; `python` → uv-compatible commands).

## Consequences

- CI and any future production Dockerfiles (§55, `infrastructure/docker/`, M15) will need their own containerization strategy for `apps/web`/`apps/api` — this ADR only covers local development, not deployment packaging.
- Anyone cloning the repo needs `pnpm` and `uv` installed (or corepack/pip-installed, as documented in the root `README.md`) in addition to Docker.

## Status

Accepted.
