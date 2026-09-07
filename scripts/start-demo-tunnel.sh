#!/usr/bin/env bash
# One-shot local demo starter: Docker services, backend, worker, frontend,
# and a Cloudflare quick tunnel — for showing a client the chatbot from
# another device. Not a production deploy; the tunnel URL is temporary and
# dies with this terminal/machine. Run from Git Bash:
#   ./scripts/start-demo-tunnel.sh
#
# Safe to re-run: Docker/backend/frontend are skipped if already up. The
# Celery worker is always restarted fresh — a long-lived worker process has
# been observed to eventually crash on Docling/torch native calls on this
# Windows machine, so "fresh worker per demo session" is a deliberate choice,
# not an oversight.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$REPO_ROOT/.demo-logs"
mkdir -p "$LOG_DIR"
CLOUDFLARED="/c/Program Files (x86)/cloudflared/cloudflared.exe"

wait_for() {
  local description="$1" check_cmd="$2" timeout_s="${3:-60}"
  local waited=0
  until eval "$check_cmd"; do
    sleep 2
    waited=$((waited + 2))
    if [ "$waited" -ge "$timeout_s" ]; then
      echo "Timed out waiting for: $description" >&2
      return 1
    fi
  done
}

echo "== Docker services =="
if ! docker info >/dev/null 2>&1; then
  echo "Starting Docker Desktop (first run can take ~60s)..."
  "/c/Program Files/Docker/Docker/Docker Desktop.exe" &
  wait_for "Docker engine" "docker info >/dev/null 2>&1" 120
fi
(cd "$REPO_ROOT" && docker compose up -d)

echo "== Backend (FastAPI) =="
if ! curl -s -o /dev/null http://localhost:8000/docs; then
  (cd "$REPO_ROOT/apps/api" && nohup python -m uv run uvicorn app.main:app --reload --port 8000 >"$LOG_DIR/backend.log" 2>&1 &)
  wait_for "backend" "curl -s -o /dev/null http://localhost:8000/docs" 60
else
  echo "Already running."
fi

echo "== Celery worker (always restarted fresh) =="
OLD_WORKER_PID=$(wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null \
  | grep -i "document_worker" | grep -i "celery" | grep -oE "[0-9]+" | tail -1 || true)
if [ -n "${OLD_WORKER_PID:-}" ]; then
  taskkill //PID "$OLD_WORKER_PID" //F >/dev/null 2>&1 || true
fi
(cd "$REPO_ROOT/workers/document_worker" && nohup python -m uv run celery -A app.celery_app worker --loglevel=info --pool=solo >"$LOG_DIR/worker.log" 2>&1 &)
wait_for "celery worker" "grep -q 'celery@.*ready' '$LOG_DIR/worker.log' 2>/dev/null" 60

echo "== Frontend (Next.js) =="
if ! curl -s -o /dev/null http://localhost:3000; then
  (cd "$REPO_ROOT/apps/web" && nohup pnpm dev >"$LOG_DIR/frontend.log" 2>&1 &)
  wait_for "frontend" "grep -qE 'Ready in|✓ Ready' '$LOG_DIR/frontend.log' 2>/dev/null" 60
else
  echo "Already running."
fi

echo "== Cloudflare tunnel =="
: >"$LOG_DIR/tunnel.log"
nohup "$CLOUDFLARED" tunnel --url http://localhost:3000 >"$LOG_DIR/tunnel.log" 2>&1 &
wait_for "tunnel URL" "grep -qo 'https://[a-zA-Z0-9.-]*trycloudflare.com' '$LOG_DIR/tunnel.log' 2>/dev/null" 30

URL=$(grep -o "https://[a-zA-Z0-9.-]*trycloudflare.com" "$LOG_DIR/tunnel.log" | head -1)
echo ""
echo "================================================================"
echo " Demo URL: $URL"
echo " Login (VIEWER, read-only): client-demo@analytics-demo.io"
echo "================================================================"
echo ""
echo "Logs: $LOG_DIR (backend.log, worker.log, frontend.log, tunnel.log)"
echo "To stop everything: ./scripts/stop-demo-tunnel.sh"
