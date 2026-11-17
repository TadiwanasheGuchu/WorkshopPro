# Monitoring

Three layers, cheapest first:

1. **Docker health checks** restart nothing by themselves but mark each service
   healthy/unhealthy (`docker compose ps`). Every service has one: PostgreSQL, Redis,
   object storage, API (`/api/v1/health/live`), worker (`celery inspect ping`), frontend
   (sign-in page), nginx (`/nginx-health`). `restart: unless-stopped` restarts crashed
   containers.
2. **`infrastructure/monitoring/check.sh`** on the server every 5 minutes (cron line in
   [installation](installation.md)). It checks:
   - every service is running and healthy;
   - the API is ready (PostgreSQL and Redis reachable);
   - the latest backup is less than `BACKUP_MAX_AGE_HOURS` (26) old;
   - disk use below `DISK_MAX_PERCENT` (85) for the app, backups and Docker data;
   - the TLS certificate is valid for at least `CERT_MIN_DAYS` (21) more days;
   - no customer notifications failed in the last 24 hours, none queued for over
     30 minutes (a stopped worker shows up here).

   It alerts through `ALERT_WEBHOOK_URL` (JSON `{"text": ...}`, the format Slack, Teams
   and Google Chat incoming webhooks accept) and/or `ALERT_EMAIL` (server `mail`
   command) only when the set of problems changes, including a "all checks OK again"
   message on recovery. Its output is logged for history.
3. **External uptime check** from outside the server (any uptime service), on
   `https://<SERVER_NAME>/api/v1/health/ready` every 1–5 minutes, expecting HTTP 200.
   This catches what the server cannot report itself: power, network, DNS, firewall.
   Its monthly uptime figure is the evidence for the 99.5% target in the maintenance
   agreement.

## Logs

- Containers write structured logs (JSON from the API, with request IDs) to Docker's
  log files, rotated at 10 MB × 5 files per service.
- `docker compose logs -f backend worker` follows the API and background jobs.
- Each API response carries `X-Request-ID`; quote it when reporting a problem.
- Passwords, tokens and message links are never logged.

## When an alert fires

| Alert | First steps |
|---|---|
| service X is not running / unhealthy | `docker compose ps`, `docker compose logs --tail 200 X`, `docker compose up -d X` |
| API is not ready | readiness detail names PostgreSQL or Redis; check that container and disk space |
| latest backup is too old | read `/var/log/workshoppro-backup.log`; run `infrastructure/backups/backup.sh` by hand |
| disk is N% full | `docker system df`; prune old images (`docker image prune`); check backup retention and the off-site copy; grow the disk |
| TLS certificate expires | Let's Encrypt: `docker compose logs certbot`; customer certificate: request renewal from their IT |
| notifications failed | Notifications screen shows the reason per message (provider error, invalid number, no consent) |
| notifications queued for over 30 minutes | worker stopped or Redis unavailable: `docker compose ps worker redis`, `docker compose logs worker` |

Verified 2026-11-17 on a production-mode stack: all checks OK; stopping the worker and
lowering the certificate threshold raised one alert with both problems, a repeat run sent
nothing, and recovery sent one "OK again" message.
