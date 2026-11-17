# Infrastructure

- `nginx/default.conf` — edge proxy used by docker-compose.yml (routing and client-IP trust boundary).
- `seaweedfs/` — S3-compatible object storage for local and single-server installs.
- `backups/` — `backup.sh`, `restore.sh` and `restore-drill.sh`. See `docs/deployment/backups.md`.

TLS and monitoring are being added in Phase 6. See `docs/development-plan.md`.
