# Installing a production server

This runbook installs WorkshopPro on one Linux server with Docker Compose, as either a
**managed dedicated installation** (our server, the workshop's domain) or a
**customer-owned on-premises installation**. Both use the same files.

Related runbooks: [backups](backups.md), [upgrades and rollback](upgrades.md),
[monitoring](monitoring.md).

## 1. Server

- Ubuntu 24.04 LTS or Debian 12, 2 vCPU, 4 GB RAM, 40 GB disk minimum (photos grow over time; plan 1 GB per few thousand inspection photos).
- Docker Engine and the Compose plugin from Docker's own repository.
- Firewall: allow 22 (SSH, restricted to known addresses), 80 and 443 only.
- Automatic security updates for the OS (`unattended-upgrades`).
- A non-root admin user in the `docker` group. Disable SSH password login.
- Server time zone can stay UTC; the app uses the organisation's time zone (default Africa/Windhoek).

## 2. Code and configuration

```bash
sudo mkdir -p /opt/workshoppro && sudo chown "$USER" /opt/workshoppro
git clone <repository-url> /opt/workshoppro
cd /opt/workshoppro
git checkout <release-tag>
cp .env.example .env
chmod 600 .env
```

Edit `.env`. Every value below is required for production; the API refuses to start in
production while any is unsafe and prints what to fix (`docker compose logs backend`).

| Setting | Value |
|---|---|
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.prod.yml` |
| `ENVIRONMENT` | `production` |
| `SERVER_NAME` | the workshop's host name, e.g. `workshop.example.com` |
| `APP_BASE_URL`, `CORS_ALLOWED_ORIGINS` | `https://<SERVER_NAME>` |
| `POSTGRES_PASSWORD`, `STORAGE_SECRET_KEY` | long random values: `openssl rand -hex 24` |
| `STORAGE_ACCESS_KEY` | any name, e.g. `workshoppro` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `EMAIL_FROM` | the workshop's or our transactional mail service |
| `WHATSAPP_*` | leave `WHATSAPP_PROVIDER=log` until the WhatsApp Business account and templates are approved |
| `BACKUP_DIR` | e.g. `/var/backups/workshoppro` |
| `ALERT_WEBHOOK_URL` and/or `ALERT_EMAIL` | where monitoring alerts go |

Leave `COOKIE_SECURE` empty (secure cookies are on in production). Keep `.env` out of
version control and record where its secrets are kept (password manager) in the
installation record.

## 3. HTTPS certificate

Certificates go in `infrastructure/certs/` (or `TLS_CERT_DIR`) as `fullchain.pem` and
`privkey.pem`. That folder is ignored by git.

**A. Public server (managed installation): Let's Encrypt.** DNS for `SERVER_NAME` must
point at the server and port 80 must be reachable.

```bash
mkdir -p infrastructure/certs
# Temporary self-signed certificate so nginx can start and serve the ACME challenge.
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=$SERVER_NAME" \
  -keyout infrastructure/certs/privkey.pem -out infrastructure/certs/fullchain.pem
docker compose up -d nginx
docker compose run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/acme \
  -d "$SERVER_NAME" --email <ops-email> --agree-tos --no-eff-email \
  --deploy-hook 'cp -L /etc/letsencrypt/live/$RENEWED_DOMAINS/fullchain.pem /etc/letsencrypt/live/$RENEWED_DOMAINS/privkey.pem /certs/'
docker compose exec nginx nginx -s reload
# Renewals from now on (checks twice a day; nginx reloads every 6 hours):
docker compose --profile letsencrypt up -d certbot
```

(`SERVER_NAME` in these commands is the shell variable; export it first or type the name.)

**B. On-premises without a public name.** Use a certificate issued by the customer's IT
(internal CA) for the name staff will type, e.g. `workshop.local`, and install that CA on
the workshop's devices. Do not ask staff to click through browser certificate warnings.
Copy the files into `infrastructure/certs/`; no certbot service is needed.

What the HTTPS edge does: port 80 redirects to HTTPS (except ACME challenges and the
health probe), TLS 1.2/1.3 only, HTTP/2, HSTS for one year. Do not set HSTS preload.

## 4. Start and create the organisation

```bash
docker compose up -d --build
docker compose ps            # all services "healthy" within about a minute
docker compose exec backend python -m app.cli create-organisation \
  --name "<Workshop trading name>" --owner-email <owner email> --owner-name "<Owner name>"
```

The owner password is prompted for. Then sign in at `https://<SERVER_NAME>` and complete
**Settings**: organisation details and logo, tax rates (as confirmed by the workshop's
accountant or tax adviser; none are pre-loaded), document numbering, branches, bays,
users and roles.

## 5. Backups and monitoring (cron)

```bash
crontab -e
```

```cron
15 1 * * *  cd /opt/workshoppro && infrastructure/backups/backup.sh >> /var/log/workshoppro-backup.log 2>&1
*/5 * * * * cd /opt/workshoppro && infrastructure/monitoring/check.sh >> /var/log/workshoppro-monitor.log 2>&1
```

Then: run `infrastructure/backups/backup.sh` once by hand, run a restore drill
(`infrastructure/backups/restore-drill.sh <backup>`), set up the off-site copy (see
[backups](backups.md)), and add an external uptime check on
`https://<SERVER_NAME>/api/v1/health/ready` (see [monitoring](monitoring.md)).
Rotate the two log files with `logrotate` (weekly, keep 8).

## 6. Hand-over checklist

- [ ] HTTPS works; `http://` redirects; certificate renewal (or expiry date) recorded.
- [ ] Owner signed in, settings completed, tax rates confirmed by the workshop's adviser.
- [ ] Test email (invite a user) received from the real mail server.
- [ ] First backup taken, restore drill passed, off-site copy verified.
- [ ] Monitoring alert tested (stop the worker for 5 minutes, then start it).
- [ ] Installation record completed: server access, `.env` secret location, backup
      destination and retention, alert recipients, maintenance agreement contacts.
