#!/usr/bin/env node
// Generates src/api-types.ts from apps/api's live OpenAPI schema.
//
// Run with the FastAPI dev server up (`uv run uvicorn app.main:app` from
// apps/api, or `pnpm dev` if the backend is proxied through it):
//
//   pnpm --filter @chatbot/schemas generate
//
// Set API_URL to point at a different backend (defaults to the local dev
// server's OpenAPI endpoint, matching apps/web's own NEXT_PUBLIC_API_URL
// default target).
import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import openapiTS, { astToString } from "openapi-typescript";

const API_URL = process.env.API_URL ?? "http://localhost:8000/openapi.json";
const OUT_PATH = fileURLToPath(new URL("../src/api-types.ts", import.meta.url));

async function main() {
  console.log(`Generating types from ${API_URL} ...`);
  const ast = await openapiTS(new URL(API_URL));
  const output = astToString(ast);
  const banner =
    "// AUTO-GENERATED — do not edit by hand.\n" +
    "// Run `pnpm --filter @chatbot/schemas generate` (with apps/api's dev\n" +
    "// server running) to regenerate from the current OpenAPI schema.\n\n";
  await writeFile(OUT_PATH, banner + output);
  console.log(`Wrote ${path.relative(process.cwd(), OUT_PATH)}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
