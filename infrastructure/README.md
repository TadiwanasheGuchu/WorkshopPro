# Infrastructure

- `nginx/default.conf` — edge proxy for local/on-premises HTTP use (routing and client-IP trust boundary).
- `nginx/templates/default.conf.template` — HTTPS edge used by `docker-compose.prod.yml`.
- `seaweedfs/` — S3-compatible object storage for local and single-server installs.
- `backups/` — `backup.sh`, `restore.sh`, `restore-drill.sh` ([docs](../docs/deployment/backups.md)).
- `deploy/` — `upgrade.sh`, `rollback.sh` ([docs](../docs/deployment/upgrades.md)).
- `monitoring/check.sh` — server health check with alerts ([docs](../docs/deployment/monitoring.md)).
- `certs/` — TLS certificate and key for production (not in git).

Start with [docs/deployment/installation.md](../docs/deployment/installation.md).
