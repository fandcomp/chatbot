import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

type Seed = {
  email: string;
  password: string;
  question: string;
  expected_article: string;
};

const SEED_PATH = path.join(__dirname, ".seed.json");

test.describe("golden path: login -> ask a question -> see a citation", () => {
  test.skip(
    !existsSync(SEED_PATH),
    `No seed data at ${SEED_PATH} — run seed.py first (see ../README.md): ` +
      "cd apps/api && uv run python ../../tests/e2e/seed.py --out ../../tests/e2e/.seed.json"
  );

  let seed: Seed;
  test.beforeAll(() => {
    seed = JSON.parse(readFileSync(SEED_PATH, "utf-8"));
  });

  test("answers a question about the seeded document with a real citation", async ({
    page,
  }) => {
    // Arrange — log in with the org seed.py just created. Waiting for
    // hydration (not just DOM presence) matters here: the login form has no
    // `name` attributes on its inputs and relies entirely on a client-side
    // onSubmit handler — clicking "Sign in" before React attaches that
    // handler falls through to a native GET form submission instead.
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await page.getByLabel(/email/i).fill(seed.email);
    await page.getByLabel(/password/i).fill(seed.password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL("/");

    // Arrange — capture the raw SSE stream's "sources" event. Asserting on
    // this (rather than only the rendered inline citation chip) verifies
    // the evidence-first pipeline itself worked — retrieval, rerank, and
    // AdaptiveCitationService — independent of whether the LLM's own prose
    // happens to follow the exact "[S1]" inline-marker format it's
    // instructed to use (a real model's format compliance is a separate,
    // non-deterministic concern this e2e test isn't trying to grade).
    const streamResponsePromise = page.waitForResponse((response) =>
      response.url().includes("/api/chat/stream")
    );

    // Act
    await page.goto("/chat");
    const composer = page.getByPlaceholder(/ask about your regulatory documents/i);
    await composer.fill(seed.question);
    await page.getByRole("button", { name: /send/i }).click();

    // Assert — evidence-first pipeline (ADR-010) must not answer from thin
    // air: the seeded document exists and is ACTIVE, so a real "insufficient
    // evidence" response here would mean retrieval/indexing regressed, not
    // just a flaky LLM phrasing difference.
    await expect(
      page.getByText(/belum ditemukan pada dokumen yang tersedia/i)
    ).not.toBeVisible({ timeout: 60_000 });

    const streamResponse = await streamResponsePromise;
    const body = await streamResponse.body();
    const sourcesMatch = body.toString("utf-8").match(/event: sources\ndata: (.+)/);
    expect(sourcesMatch, "expected a 'sources' SSE event in the chat stream").not.toBeNull();
    const sources = JSON.parse(sourcesMatch![1]) as {
      insufficient_evidence: boolean;
      citations: Record<string, { structural_path_text: string | null }>;
    };
    expect(sources.insufficient_evidence).toBe(false);
    const citationValues = Object.values(sources.citations);
    expect(citationValues.length).toBeGreaterThan(0);
    expect(
      citationValues.some((c) => (c.structural_path_text ?? "").includes(seed.expected_article))
    ).toBe(true);

    // Assert — the rendered answer is actually grounded in the seeded
    // document's real text, not a generic non-answer.
    await expect(page.getByText(/tata tertib kantor/i)).toBeVisible();
  });
});
