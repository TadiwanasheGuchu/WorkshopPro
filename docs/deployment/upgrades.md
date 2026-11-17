# Upgrades and rollback

Releases are git tags. An upgrade always takes a backup first and records a rollback
point, so it can be undone.

## Before upgrading

- Read the release notes for new settings or manual steps.
- Upgrade outside working hours; tell the workshop. Expect about a minute of downtime
  while containers restart (longer if images are built on the server).
- Check the server is healthy: `infrastructure/monitoring/check.sh`.

## Upgrade

```bash
cd /opt/workshoppro
infrastructure/deploy/upgrade.sh <release-tag>
```

`upgrade.sh`:

1. refuses to run if the checkout has local changes;
2. takes a backup and records the current commit, schema revision, backup and image
   tags in `.deploy/last-upgrade` (images are kept as `workshoppro-*:previous`);
3. checks out the tag, builds the images (`SKIP_BUILD=1` to use images built elsewhere),
   and starts the stack — the backend applies database migrations on start;
4. waits until every service is healthy and the API is ready.

Afterwards, sign in, open a job card, an invoice PDF and the dashboard, and run
`infrastructure/monitoring/check.sh`.

## Rollback

```bash
infrastructure/deploy/rollback.sh
```

- If the upgrade did not change the database schema, the previous images and commit are
  started again. No data is lost.
- If it did, the new release's migrations are reversed first (`alembic downgrade` to the
  recorded revision), then the previous release is started. Work entered since the
  upgrade is kept, except anything stored only in columns or tables the new release
  added.
- If the downgrade fails, or data is damaged, use
  `infrastructure/deploy/rollback.sh --restore-backup`, which restores the pre-upgrade
  backup. **Everything entered since the upgrade is lost**; agree this with the workshop
  and record what must be re-entered.

After a rollback the checkout is on a detached commit. Return to a release with
`git checkout <release-tag>` before the next upgrade.

Verified 2026-11-17 on a production-mode stack (HTTPS, `ENVIRONMENT=production`): upgrade
with backup and rollback point; rollback reversing a migration (0016 → 0015) and starting
the previous release, with all data intact.

## Writing migrations that can be rolled back

- Every migration has a working `downgrade()`; CI runs upgrade → downgrade → upgrade.
- Prefer additive changes (new nullable columns, new tables). Drop or rename columns in
  a later release, once the release that stopped using them is in place.
- Data migrations must be safe to run again after a downgrade and upgrade.
