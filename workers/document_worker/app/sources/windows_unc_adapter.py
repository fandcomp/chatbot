"""Production adapter for LAN-M1 (ADR-020): the worker reads a Windows UNC
path directly, since it already runs as a native Windows process (not
containerized) — see ADR-020 for the full deployment-shape reasoning.

**Not yet validated against a real SMB share** — no such share is reachable
from the environment this was built in. Exercised only via
`local_fake_adapter.py`-style tests against a real local filesystem.
See `docs/operations/LAN_CONNECTOR_RUNBOOK.md`.

Known, documented limitations (not silently mishandled):
- DFS namespace referrals are not specially resolved by `os.scandir` —
  register underlying share paths directly, not a DFS root.
- `.lnk` shortcuts are never followed — a folder of shortcuts must have
  each real target registered as its own SourceRoot.
"""

from __future__ import annotations

import os

from app.core.config import settings
from app.sources._filesystem_walk import paged_walk
from app.sources.adapter import HealthStatus, ScanPage


class UNCHostNotAllowedError(Exception):
    pass


def parse_unc_host(unc_path: str) -> str:
    """`\\\\host\\share\\sub\\path` -> `host`. Raises ValueError for anything
    that isn't a well-formed UNC path — this adapter never falls back to
    interpreting a bare path as a local drive."""
    normalized = unc_path.replace("/", "\\")
    if not normalized.startswith("\\\\"):
        raise ValueError(f"not a UNC path (must start with \\\\): {unc_path!r}")
    parts = [p for p in normalized[2:].split("\\") if p]
    if len(parts) < 2:
        raise ValueError(f"UNC path missing host or share: {unc_path!r}")
    return parts[0].lower()


class WindowsUNCAdapter:
    def __init__(self, root_path: str) -> None:
        host = parse_unc_host(root_path)
        allowed = settings.connector_allowed_hosts_list
        if allowed and host not in allowed:
            raise UNCHostNotAllowedError(
                f"host {host!r} is not in CONNECTOR_ALLOWED_HOSTS — refusing to scan "
                f"{root_path!r}. Register the host explicitly before creating this source."
            )
        self._root_path = root_path

    def check_health(self) -> HealthStatus:
        try:
            # A bare listdir is the cheapest real reachability check — it
            # exercises the actual network path, unlike a ping (which many
            # Windows file servers block anyway).
            os.listdir(self._root_path)
        except FileNotFoundError:
            return HealthStatus(healthy=False, detail=f"root not found: {self._root_path}")
        except PermissionError as exc:
            return HealthStatus(healthy=False, detail=f"access denied: {exc}")
        except OSError as exc:
            return HealthStatus(healthy=False, detail=f"unreachable: {exc}")
        return HealthStatus(healthy=True, detail="ok")

    def paged_scan(self, subtree: str, cursor: dict | None, page_size: int) -> ScanPage:
        return paged_walk(self._root_path, subtree, cursor, page_size)

    def open_stream(self, normalized_path: str):
        raise NotImplementedError("open_stream is unused until LAN-M2")
