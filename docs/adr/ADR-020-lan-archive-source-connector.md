# ADR-020: LAN Archive Source Connector — Adapter Contract and Deployment Model

## Context

A client needs the chatbot to ingest a Windows LAN file-share archive (PDF,
DOCX, and possibly legacy DOC) that can reach up to 4TB and grows over time.
The physical files may live behind one SMB share, several, a DFS namespace,
or a folder of shortcuts — the real topology is unknown until an operator
configures it. Full requirements are recorded in
`docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md`; this ADR covers one specific
architectural fork that addendum calls out explicitly: how the system
actually reaches the Windows share.

Two deployment models are possible:

1. **Windows Service connector**: a separate service running on (or with
   access to) the Windows LAN, using a service account to read UNC paths,
   which then pushes metadata/files to the backend over an authenticated
   HTTP endpoint.
2. **Direct OS-level access**: the backend/worker process itself reads UNC
   paths directly (via an OS-provided mount or native UNC path support).

The correct choice depends entirely on what OS the backend/worker actually
runs on in production — a Linux container has no native UNC/SMB access
without an explicit CIFS mount, and assuming otherwise would produce a
connector that silently does nothing in production.

## Decision

**Evidence from this repository's actual deployment shape:**
`workers/document_worker` — the process that would own any LAN discovery/
transfer work, matching this repo's existing separation of a producer-only
Celery client in `apps/api` from the actual task implementation in the
worker (ADR-016) — already runs as a **native Windows process**, not inside
Docker. ADR-016 states explicitly: "The worker is not added as a new Docker
Compose service; it runs as a native local-dev process." This session's own
tooling confirms the same shape end-to-end: `uv run celery -A app.celery_app
worker --loglevel=info --pool=solo` is run directly on this Windows machine
(`--pool=solo` itself is a Windows-specific accommodation documented in
`workers/document_worker/README.md`).

A native Windows Python process can read `\\host\share\...` UNC paths
directly via `os.scandir`/`pathlib`/`open()` with no additional relay
process, no service account handoff, and no new authenticated HTTP surface
to secure. Given the client's explicit cost sensitivity (§1 of the LAN
prompt: "Client sangat memperhatikan biaya awal dan biaya berulang"), adding
a second service (build, deploy, secure, monitor) is not justified while the
worker's actual deployment shape already has direct access.

**Decision:** LAN-M1 builds a small `Protocol`-based adapter contract
(`workers/document_worker/app/sources/adapter.py`) with two implementations:

- `LocalFakeAdapter` — reads a real local directory (or in-memory manifest)
  for tests and any dev-environment dry run. This is what every automated
  test in this repo runs against.
- `WindowsUNCAdapter` — a real `os.scandir`-based implementation reading UNC
  paths directly from the worker process, for the worker's current
  native-Windows deployment.

The adapter `Protocol` itself does not assume either deployment model — it
only requires `paged_scan`, `stat`, `open_stream`, `check_health`. A future
Windows-Service-based adapter (implementing the same `Protocol` by calling
an HTTP endpoint instead of the filesystem) is a drop-in addition, not a
redesign, if production later moves the worker to a Linux host.

**This decision is conditioned on the current deployment shape, not
permanent.** Production OS is explicitly "belum diketahui" (unknown) per the
client info table in the LAN requirements doc. If production ever runs
`workers/document_worker` in a Linux container, this ADR must be revisited
and a Windows Service connector built instead — `WindowsUNCAdapter` would
simply not function (no UNC access) and `check_health()` would report
unreachable, which is a safe (if unhelpful) failure mode rather than a
silent one.

## Alternatives

- **Build the Windows Service connector now, unconditionally**: rejected —
  more infrastructure (a new deployable, a new authenticated ingress
  endpoint, a new credential-handoff surface to secure) than the worker's
  actual current deployment shape needs. Revisit if/when production moves
  off native Windows.
- **SMB mount inside a Linux container** (e.g., a CIFS mount point provided
  by the host): rejected as the default for the same reason — not needed
  given the worker isn't containerized today, and mounting SMB inside a
  container adds its own credential and reliability surface (mount
  failures, stale handles) this repo has no operational experience with.
  Recorded as the fallback to reconsider only if a future container-based
  deployment is chosen and a Windows Service is judged too heavy for that
  context.
- **Mapped drive letter (e.g. `Z:`) instead of UNC paths**: rejected per the
  LAN requirements doc's explicit prohibition ("Jangan bergantung pada
  mapped drive pengguna seperti Z:") — drive mappings are session/user-
  scoped and not reliable for a background service account.

## Consequences

- `WindowsUNCAdapter` is implemented in LAN-M1 but **cannot be validated
  against a real SMB share** from this dev environment — no such share is
  reachable here. It is exercised only via `LocalFakeAdapter`-backed tests
  until a real Windows LAN environment is available; `docs/operations/
  LAN_CONNECTOR_RUNBOOK.md` records this explicitly as pending
  client-environment validation, not a passed test.
- If production later requires a Linux-hosted worker, a Windows Service
  connector must be designed and built as a new `Protocol` implementation —
  this ADR's contract is written so that addition doesn't require touching
  `SourceRoot`/`SourceEntry`/`ScanRun` or the discovery loop.
- `workers/document_worker/app/database.py` gains Core `Table` mirrors for
  `source_roots`/`source_entries`/`scan_runs` (whichever the worker actually
  writes), accepting the same cross-process schema-drift risk ADR-016
  already accepts for `document_versions`/`processing_jobs` — a future
  migration to these tables must update both the `apps/api` ORM model and
  the worker's Core `Table` definition.

## Status

Accepted.
