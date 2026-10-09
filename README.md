# Family Budget Manager

A responsive expense-tracking application built with Flask and SQLite. It
records actual spending only; it does not include budgets, spending limits, or
warnings. Local use remains available without a login. Production mode requires
credential-based access and a persistent database location.

## Add an expense

The expense form records an amount in PKR, an editable date defaulting to
today, and a category. Notes are optional. Available categories are School Fees, Groceries, Meat/Food, Cow Expenses, Bills,
Transport, Medical, and Other. Amounts, dates, categories, and notes are
validated on the server before they are stored.

On startup, the application creates the SQLite database and table if needed.
If an older expense table already exists, the app adds the category and notes
columns while preserving the existing expense records.

## Review and manage expenses

The expense history and daily details pages provide Edit and Delete actions.
Edits use the same server-side validation as new expenses. Delete is submitted
with POST and asks for confirmation in the browser. Daily details show totals
and record counts calculated directly from SQLite. The dashboard shows
all-time and current calendar-month spending, also queried from saved records.

## Export expenses and back up the database

Use the dashboard's export controls to download all expenses or only the
selected month as a UTF-8 CSV file. Spreadsheet formula-like text cells are
escaped during export. CSV downloads are generated for the request and are not
stored under `static/`.

Select **Create database backup** on the dashboard to create a consistent
SQLite backup using SQLite's backup API. Backups are stored locally in
`instance/backups/`, outside public static files, and each gets a unique
filename. Backup files are excluded from version control and are not
automatically deleted.

To restore a backup safely in Windows PowerShell:

1. Stop Flask with `Ctrl+C`.
2. Copy the current `instance\family_budget.sqlite3` to a separate safe
   location as a precaution.
3. Copy the chosen backup from `instance\backups\` over
   `instance\family_budget.sqlite3`.
4. Start Flask and verify the expected expense history before continuing.

Restore example, run from the project folder after stopping Flask:

```powershell
Copy-Item -LiteralPath ".\instance\family_budget.sqlite3" -Destination "$HOME\family_budget_before_restore.sqlite3"
$backup = ".\instance\backups\family-budget-backup-20261009-223000-000000-ab12cd34.sqlite3" # Replace with the backup you chose
Copy-Item -LiteralPath $backup -Destination ".\instance\family_budget.sqlite3" -Force
```

## Mobile and installable app

The layout adapts the dashboard, expense forms, history, and day details for
phone screens. On supported browsers the app can be installed from the
browser's install or add-to-home-screen menu. The service worker caches only
the static app shell and a plain offline page; it never caches expense pages or
expense data. Expense viewing and editing still require a network connection.
Service workers require HTTPS, except on localhost during development.

## Production deployment

The app has production configuration for HTTPS cookies, CSRF protection,
single-account login, safe errors, a health endpoint, Gunicorn, and an
environment-configured SQLite path. It has **not** been deployed. See
[DEPLOYMENT.md](./DEPLOYMENT.md) for the Render recommendation, environment
settings, data protection, costs/limitations, and a deployment checklist.
Do not deploy or transfer the live database until explicitly approved.

## Requirements

- Python 3.10 or later
- The one application dependency listed in `requirements.txt` (Flask)

## Run on Windows PowerShell

From the project folder, create and activate a virtual environment, install
Flask, and start the local development server:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks virtual-environment activation, run this once in the
current terminal and then activate it again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Open `http://127.0.0.1:5000` in a browser. SQLite creates its database and
expenses table automatically at `instance/family_budget.sqlite3`.

## Run tests

With the virtual environment active, run:

```powershell
python -m unittest discover -s tests -v
```

## Project structure

- `app.py` — application factory and HTTP routes.
- `config.py` — environment-based application and production defaults.
- `database/db.py` — SQLite connection lifecycle, schema initialization, and parameterized queries.
- `services/expense_service.py` — expense validation and create, read, update, and delete operations.
- `services/report_service.py` — dashboard and daily spending summaries.
- `templates/` — shared page layout, dashboard, expense form, history, day details, and not-found page.
- `static/css/style.css` — responsive visual styles.
- `static/js/app.js` — client-side enhancements and secure-context service-worker registration.
- `static/manifest.webmanifest`, `static/service-worker.js`, `static/offline.html` — install metadata and static-only offline shell.
- `static/images/` — PWA app icons.
- `tests/test_expenses.py` — focused tests for the dashboard and expense validation/routes.
- `instance/` — local SQLite database storage; database files are excluded from version control.
