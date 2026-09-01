"use client";

import { useEffect, useState } from "react";

type DependencyChecks = Record<string, string>;

type ReadyResponse = {
  status: "ok" | "degraded";
  checks: DependencyChecks;
};

type StatusState =
  | { kind: "loading" }
  | { kind: "healthy"; checks: DependencyChecks }
  | { kind: "degraded"; checks: DependencyChecks }
  | { kind: "unreachable" };

function useBackendStatus(): StatusState {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;

    async function loadStatus() {
      if (!apiUrl) {
        setState({ kind: "unreachable" });
        return;
      }

      try {
        const response = await fetch(`${apiUrl}/health/ready`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          setState({ kind: "unreachable" });
          return;
        }

        const data = (await response.json()) as ReadyResponse;
        setState(
          data.status === "ok"
            ? { kind: "healthy", checks: data.checks }
            : { kind: "degraded", checks: data.checks }
        );
      } catch {
        setState({ kind: "unreachable" });
      }
    }

    void loadStatus();
    return () => controller.abort();
  }, []);

  return state;
}

function StatusDot({ isHealthy }: { isHealthy: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${
        isHealthy ? "bg-emerald-500" : "bg-red-500"
      }`}
    />
  );
}

export function BackendStatus() {
  const status = useBackendStatus();

  if (status.kind === "loading") {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Checking backend status…
      </p>
    );
  }

  if (status.kind === "unreachable") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
        <p className="font-medium">Backend unreachable</p>
        <p className="mt-1 text-red-600 dark:text-red-400">
          Is the FastAPI dev server running on {process.env.NEXT_PUBLIC_API_URL ?? "(NEXT_PUBLIC_API_URL not set)"}?
        </p>
      </div>
    );
  }

  const isHealthy = status.kind === "healthy";

  return (
    <div
      className={`rounded-lg border px-4 py-3 text-sm ${
        isHealthy
          ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
          : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300"
      }`}
    >
      <p className="font-medium">
        Backend status: {isHealthy ? "healthy" : "degraded"}
      </p>
      <ul className="mt-2 space-y-1">
        {Object.entries(status.checks).map(([name, value]) => (
          <li key={name} className="flex items-center gap-2">
            <StatusDot isHealthy={value === "ok"} />
            <span className="font-mono">{name}</span>
            <span className="text-xs opacity-75">{value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
