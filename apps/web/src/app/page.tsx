"use client";

import Link from "next/link";

import { BackendStatus } from "@/components/BackendStatus";
import { useAuth } from "@/lib/auth-context";

function AuthStatus() {
  const { state, logout } = useAuth();

  if (state.status === "loading") {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Checking session…</p>;
  }

  if (state.status === "unauthenticated") {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        <Link href="/login" className="text-primary underline-offset-4 hover:underline">
          Sign in
        </Link>{" "}
        or{" "}
        <Link href="/register" className="text-primary underline-offset-4 hover:underline">
          register your organization
        </Link>
        .
      </p>
    );
  }

  return (
    <p className="text-sm text-zinc-600 dark:text-zinc-400">
      Signed in as {state.user.email} ({state.role}).{" "}
      <Link href="/documents" className="text-primary underline-offset-4 hover:underline">
        Documents
      </Link>{" "}
      <button
        type="button"
        onClick={() => void logout()}
        className="text-primary underline-offset-4 hover:underline"
      >
        Sign out
      </button>
    </p>
  );
}

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-6 font-sans dark:bg-black">
      <main className="flex w-full max-w-xl flex-col items-center gap-6 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
          Self-Service Regulatory Knowledge Assistant
        </h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          AI regulatory assistant that gives verified answers, traceable
          directly to the source document, its structure, and page.
        </p>
        <AuthStatus />
        <div className="w-full">
          <BackendStatus />
        </div>
      </main>
    </div>
  );
}
