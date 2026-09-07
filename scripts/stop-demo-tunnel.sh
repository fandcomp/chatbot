#!/usr/bin/env bash
# Stops everything started by start-demo-tunnel.sh: the Cloudflare tunnel,
# frontend, backend, and Celery worker. Docker services are left running
# (cheap to keep up; `docker compose down` if you want them stopped too).

set -uo pipefail

kill_by_commandline_match() {
  local description="$1" pattern="$2"
  local pids
  pids=$(wmic process where "name='python.exe' or name='node.exe' or name='cloudflared.exe'" get ProcessId,CommandLine 2>/dev/null \
    | grep -i "$pattern" | grep -oE "[0-9]+" || true)
  for pid in $pids; do
    taskkill //PID "$pid" //F >/dev/null 2>&1 && echo "Stopped $description (PID $pid)"
  done
}

kill_by_commandline_match "Cloudflare tunnel" "cloudflared"
kill_by_commandline_match "Celery worker" "document_worker.*celery"
kill_by_commandline_match "Backend (uvicorn)" "uvicorn"
kill_by_commandline_match "Frontend (next dev)" "next.*dev\|pnpm.*dev"

echo "Done. Docker services (Postgres/Redis/Qdrant/MinIO) are still running — run 'docker compose down' from the repo root to stop those too."
