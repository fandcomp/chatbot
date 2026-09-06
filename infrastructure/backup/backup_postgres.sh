#!/usr/bin/env bash
# Backup script (spec §98/M15) for the PostgreSQL source of truth (ADR-001).
#
# Scope note: only Postgres is backed up here. Qdrant is a derived index
# (ADR-002 — every retrieval query re-verifies against Postgres live; a lost
# Qdrant collection is rebuilt by re-running the indexing worker against
# document_chunks, not restored from a backup). Redis holds only the rate
# limiter's counters and, as of M15, the answer cache — both fine to lose
# and rebuild from zero. Original uploaded files live in S3/MinIO; back
# those up via your object-storage provider's own bucket versioning or
# cross-region replication, not with this script (a from-scratch mc-based
# sync script for a dev-only MinIO container would be more fragile than
# useful — production deployments should use their provider's native
# feature here).
#
# Usage:
#   ./infrastructure/backup/backup_postgres.sh [output_dir]
#
# Requires: the `chatbot-postgres` container from the root docker-compose.yml
# already running (`docker compose up -d`).

set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
CONTAINER_NAME="chatbot-postgres"
POSTGRES_USER="${POSTGRES_USER:-chatbot}"
POSTGRES_DB="${POSTGRES_DB:-chatbot}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${OUTPUT_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

mkdir -p "${OUTPUT_DIR}"

echo "Backing up '${POSTGRES_DB}' from container '${CONTAINER_NAME}' to ${OUTPUT_FILE} ..."
docker exec "${CONTAINER_NAME}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --format=plain \
  | gzip > "${OUTPUT_FILE}"

echo "Done: $(du -h "${OUTPUT_FILE}" | cut -f1) written."
