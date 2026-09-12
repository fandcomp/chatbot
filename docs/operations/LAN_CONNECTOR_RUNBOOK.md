# LAN Connector Runbook

Operational guide for the Windows LAN archive source connector
(`docs/ADDENDUM_LAN_ARCHIVE_4TB_COST_CONTROL.md`, `docs/adr/ADR-020-lan-archive-source-connector.md`).
Covers registration and discovery (LAN-M1) specifically — for promotion,
budget configuration, retrieval/access, backup/restore, rollback, and
staged rollout across the whole pipeline, see
`docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md`.

## Status: not yet field-validated

Everything in this runbook describes the **intended** setup for
`WindowsUNCAdapter`. It has been exercised only via unit tests against a real
local filesystem — **no real Windows UNC/SMB share has been reachable from
the development environment this was built in.** Treat every step below as
untested against production conditions until an operator confirms
otherwise, and record that confirmation in `docs/LAN_ARCHIVE_PROGRESS.md`.

## Prerequisites

- `workers/document_worker` must run as a **native Windows process** (not
  inside a Linux container) — this is the deployment shape ADR-020's
  decision is conditioned on. If the worker ever moves to a Linux host,
  stop here and revisit ADR-020 before proceeding; `WindowsUNCAdapter` has
  no UNC access from Linux.
- A dedicated **read-only** service account with access to the target
  share(s). Do not reuse an interactive user account.
- The share(s) to be scanned, identified by explicit UNC path
  (`\\host\share\subpath`) — never a mapped drive letter.

## Registering a source

1. Confirm the service account can read the target share interactively
   first (e.g., `dir \\host\share` from a command prompt running as that
   account) before registering it in the system.
2. Register a `SourceRoot` via `POST /sources` (OWNER/ADMIN role) with
   `source_type=WINDOWS_UNC`, the UNC root, and an explicit allowlist of
   subtrees if the share should not be scanned in full.
3. Trigger a scan via `POST /sources/{id}/scan` and check `GET
   /sources/{id}/scan-runs` for status. A `partial` status with recorded
   subtree errors is expected and safe — it means some subtrees were
   inaccessible, not that the whole scan failed.
4. Review `GET /sources/{id}/entries` before doing anything else with this
   source. This is catalog-only: no content has been read, extracted, or
   copied at this point.

## Known limitations (documented, not silently handled)

- **DFS referrals**: `os.scandir`/`pathlib` do not specially resolve DFS
  namespace referrals. If the target is a DFS namespace, register the
  underlying share paths directly rather than the DFS root, until this is
  explicitly tested.
- **Symlinks/reparse points**: the discovery scan does not follow
  filesystem reparse points outside the registered root — this prevents
  scan loops but means a reparse point pointing elsewhere is reported as
  present-but-not-traversed, not silently followed.
- **Shortcuts (`.lnk`)**: never followed automatically. A folder that is
  actually a collection of shortcuts to other shares will only show the
  `.lnk` files themselves as catalog entries — register each real target
  share as its own `SourceRoot` instead.
- **File locks / in-progress copies**: LAN-M1 only catalogs metadata; it
  does not open file contents, so lock contention is not yet a concern.
  This becomes relevant starting LAN-M2 (snapshot/transfer).
- **Disabling a misconfigured source**: `POST /sources/{id}/disable`
  (OWNER/ADMIN) stops it from accepting new scans/promotions — `POST
  /sources/{id}/scan` and `POST /sources/{id}/entries/promote` both return
  409 while disabled. It never deletes the source or any already-promoted
  documents; if some of those shouldn't stay active, archive them
  separately (`POST /documents/{id}/archive`) — see
  `docs/evaluation/LAN_ARCHIVE_PILOT_PLAN.md`'s rollback plan.
  `POST /sources/{id}/enable` reverses it.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `SourceRoot.health = unreachable` | Host down, network path blocked, service account lacks access | Check `check_health()` result detail; verify account access manually first |
| `ScanRun.status = partial` with subtree errors | Some subtrees access-denied or transiently unreachable | Expected — review recorded errors per subtree; does not require re-registering the whole source |
| No new entries after known file additions | Scan not yet re-run, or added files outside the registered subtree allowlist | Trigger a new scan; verify the allowlist covers the new location |

## Escalation

If field validation against a real share surfaces behavior not covered
here (permission model differences, unexpected DFS behavior, performance
issues at scale), record findings in `docs/LAN_ARCHIVE_PROGRESS.md` under
"Assumptions not yet validated" before changing the adapter implementation,
so the next session has the full context.
