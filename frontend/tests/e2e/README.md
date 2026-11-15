# End-to-end tests

Run against the full Docker Compose stack (nginx, frontend, backend, Mailpit).

```bash
docker compose up -d --build
docker compose exec backend python -m app.cli create-organisation \
  --name "E2E Workshop" --owner-email e2e-owner@example.com --owner-name "E2E Owner"
cd frontend
E2E_OWNER_EMAIL=e2e-owner@example.com E2E_OWNER_PASSWORD='<password you chose>' npm run e2e
```

Environment variables:

| Variable | Default |
|---|---|
| `E2E_BASE_URL` | `http://localhost:3000` |
| `E2E_MAILPIT_URL` | `http://localhost:8025` |
| `E2E_OWNER_EMAIL` / `E2E_OWNER_PASSWORD` | required |

Tests create uniquely named users on each run, so they can be re-run against the same database.
