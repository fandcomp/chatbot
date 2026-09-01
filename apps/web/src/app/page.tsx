import { BackendStatus } from "@/components/BackendStatus";

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
        <div className="w-full">
          <BackendStatus />
        </div>
      </main>
    </div>
  );
}
