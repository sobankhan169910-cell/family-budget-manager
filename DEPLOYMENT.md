# Production deployment guide

## Recommendation and current status

For this small, single-household Flask + SQLite app, Render is a practical
first host because it supports Flask web services, managed HTTPS, and a
persistent disk. Use one paid Web Service instance with its persistent disk
mounted at `/var/data`. The app is configured to refuse production startup if
the login, HTTPS cookie, or persistent-data settings are missing or unsafe.

This repository is **prepared for deployment, not deployed**. No Render service
has been created, no public URL has been issued, and the local SQLite database
has not been uploaded. Do not proceed to a public deployment or transfer real
records until the owner explicitly approves that step.

## Hosting costs and constraints

As checked on **2026-10-09**, Render's [pricing page](https://render.com/pricing)
lists its smallest paid web-service compute plan at **$7/month** (512 MB RAM)
and persistent SSD storage at **$0.25 per GB/month**. The ongoing estimate is
therefore:

```text
$7/month compute + (selected persistent disk size in GB × $0.25/month)
```

For example, if a 1 GB disk is available for selection, the listed baseline
would be about **$7.25/month**, before taxes or any usage-based charges. The
Dashboard's displayed quote at service creation is authoritative; verify it
before confirming because Render can change prices and disk-size options.

- Render's Free web-service plan costs $0 and lists 512 MB RAM, but it cannot
  have a persistent disk. Its filesystem is ephemeral, so SQLite records can
  disappear on a restart or redeploy. Free services can also spin down when
  idle and have a monthly included-hours limit. This is not safe for real
  family records.
- A persistent disk is available only with a paid web service. Budget for both
  compute and disk; disk cost depends on the size selected in the Dashboard.
- The disk mount is the only durable filesystem area. Data elsewhere in the
  container is ephemeral. Disk size can be increased but not decreased.
- A Render persistent disk is attached to one service instance; it prevents
  multi-instance scaling and zero-downtime deploys. A restart/redeploy can
  cause a short interruption. SQLite is appropriate here only while this
  single-instance constraint is acceptable.
- Render documents automatic daily disk snapshots retained for at least seven
  days, but snapshots are whole-disk recovery aids, not a replacement for
  application-level SQLite backups. A disk snapshot restore rolls back all
  disk changes made after that snapshot.

References: [Render Flask deployment](https://render.com/docs/deploy-flask),
[web services and HTTPS](https://render.com/docs/web-services),
[persistent disks and limitations](https://render.com/docs/disks), and
[free-instance limitations](https://render.com/docs/free).

## Before connecting a Git repository

The current workspace does not have a Git repository. If preparing one after
approval, keep the real database and backups out of version control:

1. Review `.gitignore` and ensure the actual database, SQLite sidecars,
   `instance/`, backups, `.env` files, and secrets are ignored.
2. Do not use `git add -f` for any database, backup, or secret file.
3. Stage the application code explicitly and inspect `git status --short`
   before committing or pushing. A private code repository does not make
   uploading the real financial database safe or necessary.
4. Configure credentials only in Render's environment-variable dashboard.
   Never paste credentials into chat, source code, commit history, or logs.

## Render service settings

After explicit approval to create a public service, in the Render Dashboard:

1. Choose **New > Web Service** and connect the reviewed code repository.
2. Select a paid single-instance plan. Do not choose the Free plan for the
   database-backed production app.
3. Set **Build Command** to:

   ```text
   pip install -r requirements.txt
   ```

4. Set **Start Command** to:

   ```text
   gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 app:app
   ```

5. Add a persistent disk with mount path `/var/data`. Select the smallest
   available size that safely holds the database and retained backups; check
   disk usage and price before saving. Do not store the database in the source
   checkout or under `static/`.
6. Set the health-check path to `/healthz`.
7. Add these environment variables. Treat secret-valued entries as secrets in
   the Render Dashboard:

   | Name | Value |
   | --- | --- |
   | `APP_ENV` | `production` |
   | `AUTH_REQUIRED` | `true` |
   | `SECRET_KEY` | Generate a new random value locally; do not reuse a source-code value. |
   | `APP_USERNAME` | A private login name chosen by the owner. |
   | `APP_PASSWORD_HASH` | A Werkzeug password hash; do not store the raw password here. |
   | `PERSISTENT_DATA_DIR` | `/var/data` |
   | `DATABASE_PATH` | `/var/data/family_budget.sqlite3` |
   | `BACKUP_DIRECTORY` | `/var/data/backups` |
   | `PYTHON_VERSION` | `3.12.12` (or another currently supported Python 3.12 patch version). |

   Generate a secret key in PowerShell without putting it into command history:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Generate a password hash with hidden interactive password input:

   ```powershell
   $hash = .\.venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('App password: ')))"
   $hash
   ```

   Copy the printed hash directly into Render's `APP_PASSWORD_HASH` secret
   field. Do not send it in chat or commit it. Use a unique, long password and
   a unique `SECRET_KEY`; store them in the owner's password manager.

8. Verify Render's HTTPS URL and `/healthz` after deployment. Render terminates
   TLS at its managed edge and redirects HTTP requests to HTTPS. The app trusts
   the single Render proxy hop for the forwarded HTTPS scheme and sets Secure,
   HttpOnly, SameSite=Lax session cookies and HSTS on HTTPS responses.

The app creates the existing SQLite schema at runtime under
`DATABASE_PATH`; the Render disk is available at runtime, not during build.
Do not run a database initialization or migration against the local real
database as part of deployment. No schema change is required for this setup.
Production startup verifies that `PERSISTENT_DATA_DIR` is a mounted filesystem
and refuses to start if it is not.
Login attempts are limited to five per minute in the single Gunicorn process.
Keep one worker and one Render service instance while this in-memory limiter
and SQLite are in use; changing to multiple workers/instances requires a
shared rate-limit store and a database designed for concurrent scaling.

## Data migration and privacy gate

The recommended first deployment is an **empty test database** on the mounted
disk. Confirm login, HTTPS, health checks, forms, exports, backups, and restore
procedures using disposable test data. Do not transfer the existing family
database as part of that first test.

Moving the real records online is a separate sensitive action. It requires
explicit approval, a verified local backup, a secure private transfer method,
and confirmation that the public URL is protected by the production login.
Never commit or serve the database/backup as a download. This project does not
perform that transfer automatically.

## Backups and restore

The authenticated dashboard's **Create database backup** button writes a
consistent SQLite backup to `/var/data/backups/`. Filenames are unique and
old backups are not automatically removed. Periodically make an additional
encrypted copy under the owner's control using a private transfer mechanism;
do not use a public URL.

For a restore, first schedule a maintenance window and ensure the Gunicorn
process is stopped so no request can write to SQLite. Keep the service and its
disk private during the operation. In a host shell with access to the mounted
disk, substitute the exact selected backup filename and run:

```sh
python -c "import sqlite3; c=sqlite3.connect('file:/var/data/backups/SELECTED_BACKUP.sqlite3?mode=ro', uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
cp -p /var/data/family_budget.sqlite3 /var/data/family_budget.pre-restore.sqlite3
cp -p /var/data/backups/SELECTED_BACKUP.sqlite3 /var/data/family_budget.restore.tmp
python -c "import sqlite3; c=sqlite3.connect('file:/var/data/family_budget.restore.tmp?mode=ro', uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()"
mv /var/data/family_budget.restore.tmp /var/data/family_budget.sqlite3
```

Continue only if both integrity checks print `ok`. Restart the service and
verify the expected record counts and totals privately. Retain the pre-restore
copy until the restored app is verified. If Render does not provide a safe way
to stop the app while retaining disk access, do not replace the database
through a live shell; obtain host support or arrange an approved maintenance
procedure first.

## Pre-publication checklist

- [ ] Owner explicitly approved public hosting and the planned data scope.
- [ ] No live database, backup, password, password hash, or secret is staged in
      the code repository.
- [ ] A verified local SQLite backup exists before any approved data transfer.
- [ ] Paid one-instance web service and persistent disk are selected and
      their current costs are understood.
- [ ] `/var/data` is mounted and all database/backup paths are under it.
- [ ] Production login, CSRF validation, secure cookies, HTTPS, and `/healthz`
      have been tested using disposable data.
- [ ] Mobile pages and PWA behavior have been checked on the target phone.
- [ ] Backup and recovery steps are documented and an off-host encrypted
      backup copy is planned.
- [ ] The resulting HTTPS URL has been checked privately before sharing it.
