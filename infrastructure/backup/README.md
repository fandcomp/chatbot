# Backup / Restore (M15)

`backup_postgres.sh` dumps the PostgreSQL source of truth (ADR-001) to a
timestamped, gzip-compressed `.sql.gz` file. `restore_postgres.sh` reverses
it (destructive — drops and recreates the target database first).

Neither script is scheduled or wired into CI here — this milestone ships
the tooling and the invalidation reasoning (see the scripts' own comments
for what is and isn't covered: Postgres only, not Qdrant or object
storage), not a production backup schedule. Wire `backup_postgres.sh` into
your own cron/scheduler and off-host the output — a backup that never
leaves the same disk as the database it backs up protects against nothing.

```bash
./infrastructure/backup/backup_postgres.sh ./backups
./infrastructure/backup/restore_postgres.sh ./backups/chatbot_20260906T120000Z.sql.gz
```
