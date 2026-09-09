# Cross-app e2e (Playwright)

One golden-path test against a REAL running stack — no mocks. See
`docs/KNOWN_LIMITATIONS.md` for what this does *not* cover yet (the full
upload → approve → publish pipeline) and why.

## Prerequisites

All of these running at once, in this order:

1. `docker compose up -d` (repo root) — Postgres/Redis/Qdrant/MinIO.
2. `apps/api`: `uv run uvicorn app.main:app --port 8000`
3. `workers/document_worker`: `uv run celery -A app.celery_app worker --loglevel=info --pool=solo`
4. `apps/web`: `pnpm dev` (or `pnpm build && pnpm start` to test the production CSP path)

Real `VOYAGE_API_KEY` and `HF_TOKEN` credentials configured in `apps/api`'s
environment (same requirement as `tests/rag_eval/evaluate.py`) — the seed
script runs the actual Docling → M4 → M5 → M6 pipeline, not a stub.

## Running

```bash
# One-time: install Playwright's browser binary
cd tests/e2e && pnpm exec playwright install chromium

# Seed a fresh org + one real ACTIVE document (takes ~10-60s)
cd apps/api
uv run python ../../tests/e2e/seed.py --out ../../tests/e2e/.seed.json

# Run the test
cd ../../tests/e2e
pnpm exec playwright test
```

`.seed.json` is git-ignored (fresh credentials + document id per seed run).
Re-run `seed.py` whenever you want a clean document; the test itself reads
whatever `.seed.json` currently contains and skips itself with a clear
message if the file is missing.

## Why this test asserts on the raw SSE response, not just the DOM

The golden path checks the streamed `sources` SSE event's `citations`
payload directly (via `page.waitForResponse`) rather than only asserting a
clickable inline citation chip rendered in the chat bubble. A real LLM's
prose doesn't always follow the exact `[S1]` inline-citation marker format
`app/chat/inline_citation_parser.py` expects — chip rendering depends on
that formatting compliance, which is a separate, non-deterministic model
concern this test isn't trying to grade (the same reason
`tests/rag_eval/evaluate.py`'s `citation_accuracy` metric exists rather than
assuming 100%). Asserting on the underlying SSE payload verifies the actual
thing this test is meant to catch a regression in: retrieval, reranking, and
`AdaptiveCitationService` actually producing a real citation grounded in the
seeded document.
