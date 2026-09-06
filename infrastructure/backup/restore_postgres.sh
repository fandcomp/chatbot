#!/usr/bin/env bash
# Restores a backup produced by backup_postgres.sh. DESTRUCTIVE: drops and
# recreates the target database before loading the dump — never run this
# against a database you have not deliberately chosen to overwrite.
#
# Usage:
#   ./infrastructure/backup/restore_postgres.sh path/to/chatbot_TIMESTAMP.sql.gz

set -euo pipefail

BACKUP_FILE="${1:?Usage: restore_postgres.sh path/to/backup.sql.gz}"
CONTAINER_NAME="chatbot-postgres"
POSTGRES_USER="${POSTGRES_USER:-chatbot}"
POSTGRES_DB="${POSTGRES_DB:-chatbot}"

echo "This will DROP and recreate database '${POSTGRES_DB}' in container '${CONTAINER_NAME}'."
read -r -p "Type the database name to confirm: " CONFIRMATION
if [[ "${CONFIRMATION}" != "${POSTGRES_DB}" ]]; then
  echo "Confirmation did not match. Aborting."
  exit 1
fi

docker exec "${CONTAINER_NAME}" psql -U "${POSTGRES_USER}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" \
  -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

gunzip -c "${BACKUP_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "Restore complete. Run 'alembic upgrade head' from apps/api if the backup predates the current migration head."
