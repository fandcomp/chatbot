import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import { AuthProvider } from "@/lib/auth-context";

describe("Home page", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "ok",
          checks: { postgres: "ok", redis: "ok", qdrant: "ok", minio: "ok" },
        }),
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the product heading", () => {
    // Arrange & Act
    render(
      <AuthProvider>
        <Home />
      </AuthProvider>
    );

    // Assert
    expect(
      screen.getByRole("heading", {
        name: /self-service regulatory knowledge assistant/i,
      })
    ).toBeInTheDocument();
  });
});
