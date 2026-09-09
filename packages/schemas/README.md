# @chatbot/schemas

Shared contract types between `apps/api` and `apps/web` — TypeScript types
generated from the FastAPI backend's OpenAPI schema via
[`openapi-typescript`](https://openapi-ts.dev/).

## Regenerating

With `apps/api`'s dev server running (`uv run uvicorn app.main:app` from
`apps/api`, port 8000 by default):

```bash
pnpm --filter @chatbot/schemas generate
```

This overwrites `src/api-types.ts` (auto-generated, do not hand-edit) from
the live `/openapi.json` schema. Point at a different backend with
`API_URL=https://staging.example.com/openapi.json pnpm --filter
@chatbot/schemas generate`.

## Adoption status

This package exists as of the M15 hardening pass (2026-09) — `apps/web`'s
existing hand-written Zod schemas (`src/lib/*-schemas.ts`) were **not**
migrated wholesale; that's a larger, separate effort (each migration needs
to verify the generated type and the Zod schema actually agree on runtime
validation, not just shape). So far only the document-relations types
(`components["schemas"]["DocumentRelationPublic"]`,
`components["schemas"]["CreateRelationRequest"]`) are consumed from here
(`apps/web/src/lib/documents-api.ts`) as a proof of concept for the
pattern. See `docs/KNOWN_LIMITATIONS.md` for the incremental-migration plan
for the rest.

See `docs/MASTER_DEVELOPMENT_SPEC.md` §35-38 for the original scope note
this package was reserved against.
