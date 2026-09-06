# Self-Service Regulatory Knowledge Assistant

An AI regulatory assistant that gives verified, traceable answers — directly linked to the source document, its structure, and page — built on an **Adaptive Structure-Aware Contextual Hybrid RAG** pipeline. Structure is generic-first: chapter/article/clause/letter (BAB/Pasal/Ayat/Huruf) is one specialized grammar among several a document region can use, not an assumed universal shape (see [`ADR-014`](docs/adr/ADR-014-region-based-generic-structure.md)).

Full architecture, product definition, and engineering rules live in [`docs/MASTER_DEVELOPMENT_SPEC.md`](docs/MASTER_DEVELOPMENT_SPEC.md) — that document is the source of truth for this project, extended by [`docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md`](docs/ADDENDUM_ADAPTIVE_MIXED_STRUCTURE_DOCUMENTS.md) (mixed-structure document handling — relevant from M3/M4 onward). Architecture decisions are recorded in [`docs/adr/`](docs/adr/).

## Quickstart

```bash
cp .env.example .env                          # defaults already work for local dev
cp apps/web/.env.example apps/web/.env.local   # Next.js only reads env files from its own dir
docker compose up -d                           # Postgres, Redis, Qdrant, MinIO
pnpm install                                   # installs apps/web workspace deps

# Terminal 1 — frontend
pnpm --filter web dev         # http://localhost:3000

# Terminal 2 — backend
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000
```

Verify the stack is wired together: open `http://localhost:3000` — the homepage calls the backend's `/health/ready` endpoint and shows live status for Postgres/Redis/Qdrant/MinIO.

## Repository structure

| Path | Purpose |
|---|---|
| `apps/web` | Next.js + TypeScript frontend (App Router, Tailwind, shadcn/ui) |
| `apps/api` | FastAPI + Python backend |
| `workers/document_worker` | Celery document processing worker (M2+) |
| `packages/schemas` | Shared OpenAPI-generated types (M9+) |
| `packages/shared` | Shared cross-app utilities |
| `infrastructure/docker` | Additional Dockerfiles beyond the root Compose file |
| `infrastructure/migrations` | Non-Alembic infra setup scripts |
| `docs/` | Master spec + architecture decision records |
| `tests/` | Cross-app e2e tests and RAG evaluation harness (M11+) |

## Milestone tracker

Per `docs/MASTER_DEVELOPMENT_SPEC.md` §98:

| Milestone | Target | Status |
|---|---|---|
| M0 | Foundation (monorepo, Next.js, FastAPI, Postgres, Redis, Qdrant, MinIO, Docker Compose, config, logging, health checks, test foundation) | Done |
| M1 | Authentication + Multi-Tenant | Done |
| M2 | Document Upload + Storage | Done |
| M3 | Generic Document Parsing — region-based, see [`ADR-014`](docs/adr/ADR-014-region-based-generic-structure.md) | Done |
| M4 | Regulatory Structure — region-based, see [`ADR-014`](docs/adr/ADR-014-region-based-generic-structure.md) | Done |
| M5 | Hierarchical Chunking | Done |
| M6 | Indexing | Done |
| M7 | Retrieval | Done |
| M8 | Reranking | Done |
| M9 | LLM Integration | Done |
| M10 | Verification + Citation | Done |
| M11 | Chat UI | Done (backend: conversations, session memory, `/chat`+`/chat/stream`; frontend: sidebar, streaming conversation view, composer, source drawer — PDF viewer/mobile polish/feedback deferred, see commit) |
| M12 | Admin Document UI | Done (upload/status/review were already built in M2-M4; this milestone added Test Knowledge — `POST /knowledge/test`, document-scoped retrieval bypassing the ACTIVE filter, and the admin preview UI. Publish/archive/versioning deferred to M13, see commit) |
| M13 | Knowledge Versioning | Not Started |
| M14 | Analytics | Not Started |
| M15 | Production Hardening | Not Started |

Per spec §107/§108: one milestone is implemented at a time, and work does not proceed to the next milestone automatically.

## Tooling

- **JS/TS**: pnpm workspaces (see [`ADR-013`](docs/adr/ADR-013-development-tooling.md))
- **Python**: uv
- **Infra**: Docker Compose (Postgres, Redis, Qdrant, MinIO — infra only, apps run locally)

## Environment variables

See [`.env.example`](.env.example) at repo root for the full list (mirrors spec §91, plus a few pragmatic additions called out inline).
