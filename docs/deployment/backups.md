# Backups and restore

WorkshopPro keeps business data in two places, and a backup must cover both:

| Data | Where | Backed up by |
|---|---|---|
| Customers, vehicles, jobs, quotations, invoices, payments, stock ledger, audit log, settings | PostgreSQL | `pg_dump` (custom format) |
| Inspection photos and other uploads | Object storage (SeaweedFS in Compose, or a managed S3 service) | `python -m app.cli storage-export` through the S3 API |

Redis is **not** backed up. It holds the background job queue, rate-limit counters and cache. After a restore, notifications that were waiting in the queue are picked up again by the `requeue_stale` sweep (every 5 minutes), because their state lives in PostgreSQL.

## What a backup contains

`infrastructure/backups/backup.sh [backup-root]` writes `<backup-root>/<UTC timestamp>/`:

- `database.dump` — the whole database.
- `objects.tar` — every stored file, with its content type.
- `manifest.json` — schema revision and row count per table, read **in the same database snapshot as the dump**, plus the number of stored files. Restores are checked against it.
- `SHA256SUMS` — checksums; `restore.sh` refuses a backup that does not match.

The folder is written as `<timestamp>.partial` and renamed only when complete, so a half-written backup is never mistaken for a good one. Files are created readable by the owner only (`umask 077`). Backups older than `BACKUP_KEEP_DAYS` (default 14) are deleted at the end of each run.

The database stays online during a backup; staff can keep working.

## Schedule (managed or on-premises server)

Run daily from the host's crontab, outside working hours (times are server time):

```bash
15 1 * * * cd /opt/workshoppro && BACKUP_KEEP_DAYS=14 infrastructure/backups/backup.sh /var/backups/workshoppro >> /var/log/workshoppro-backup.log 2>&1
```

A backup on the same disk does not survive the loss of that server. **Copy each backup off the server** (another site, or an S3 bucket in another region) with the tool agreed in the maintenance agreement, for example `rclone copy` or `rsync` over SSH, and encrypt it at rest if the destination is not under the workshop's control. The off-site destination, its retention and who holds the keys must be written into the installation record for each customer.

Check the log daily (monitoring alerts on a missing or failed backup are covered in the monitoring runbook).

## Restoring

```bash
infrastructure/backups/restore.sh /var/backups/workshoppro/20261117T013000Z
```

The script:

1. Checks the checksums.
2. Asks you to type the Compose project name (skip with `--yes` in scripts).
3. Stops the app, **replaces the database**, restores it from `database.dump`.
4. Starts the backend, which applies any newer migrations (restoring an older backup onto a newer release is supported; the reverse is not).
5. Puts every file from `objects.tar` back into object storage.
6. Runs `python -m app.cli verify-restore`, which checks:
   - row counts match the manifest (a restore onto a newer schema allows data migrations to add rows);
   - stock on hand equals the stock movement ledger, and reserved stock equals open reservations;
   - each invoice's amount paid equals its payment allocations, and amount credited equals its credit notes;
   - every stored file referenced by the database exists in object storage.
7. Starts the rest of the app only if verification passes. If it fails, the app stays stopped (backend up for inspection) and the output names the problem.

Sessions are restored too, so anyone signed in at backup time can be signed in again. After restoring because of a security incident, also deactivate and re-invite affected users.

## Restore drill (do this monthly and after every upgrade)

```bash
infrastructure/backups/restore-drill.sh /var/backups/workshoppro/<latest>
```

This starts a separate, empty Compose project (`workshoppro-restore-drill`, web on port 3901), restores the backup into it, verifies it, checks the API and sign-in page answer, and then deletes the drill project and its volumes. The live installation is not touched. Use `--keep` to leave it running and sign in at `http://<server>:3901` to look around; remove it afterwards with:

```bash
COMPOSE_PROJECT_NAME=workshoppro-restore-drill docker compose down -v
```

Record the date, backup used and result of each drill in the installation record.

Last verified: 2026-11-17 — backup of the development Compose install (97 job cards, 2 stored files) restored into the drill project in 81 seconds; all six checks passed; the owner signed in and saw all 97 job cards. A backup with a modified `objects.tar` was refused at the checksum step.

## Using a managed S3 service instead of SeaweedFS

The object export goes through the S3 API using the same `STORAGE_*` settings as the app, so the scripts work unchanged. If the provider offers versioning or its own snapshots, keep them on as a second line of defence, but still take these backups: they are what `restore.sh` and the drill understand.
