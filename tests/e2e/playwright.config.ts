import { defineConfig, devices } from "@playwright/test";

// Cross-app e2e against a stack the developer already has running (docker
// compose + apps/api + document_worker + apps/web) — see ../README.md for
// the full run order. No webServer here: unlike a single-app e2e setup,
// this needs three separate processes (API, worker, frontend) that
// Playwright itself has no business owning the lifecycle of.
export default defineConfig({
  testDir: ".",
  // A real chat turn against this test's document runs the FULL evidence-
  // first pipeline (retrieval, rerank, a real GPT-OSS LLM call streamed
  // token-by-token) — 30s (Playwright's default) is not enough headroom.
  timeout: 90_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_WEB_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
