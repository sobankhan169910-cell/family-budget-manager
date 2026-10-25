import os
import sqlite3

from flask import current_app, g


# Columns returned to the rest of the application. ``note`` is a
# backwards-compatible alias of ``notes`` so that the existing templates keep
# working unchanged.
DEFAULT_MEMBER = "Soban Khan"

EXPENSE_COLUMNS = (
    "id",
    "amount_cents",
    "category",
    "description",
    "notes",
    "notes AS note",
    "member",
    "sync_id",
    "expense_date",
    "created_at",
)

_SELECT_EXPENSES = "SELECT " + ", ".join(EXPENSE_COLUMNS) + " FROM expenses"


def get_db():
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        os.makedirs(
            os.path.dirname(database_path) or current_app.instance_path,
            exist_ok=True,
        )
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    connection = get_db()
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Other',
            notes TEXT NOT NULL DEFAULT '',
            member TEXT NOT NULL DEFAULT 'Soban Khan',
            sync_id TEXT DEFAULT NULL,
            expense_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_expenses_expense_date
        ON expenses (expense_date);
        """
    )
    existing_columns = {
        column["name"]
        for column in connection.execute("PRAGMA table_info(expenses)").fetchall()
    }
    # Older deployments may still have a ``budget_id`` column that was added
    # outside this module. It is intentionally left in place: dropping it would
    # destroy data that is not owned by this application.
    if "category" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'"
        )
    if "notes" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN notes TEXT NOT NULL DEFAULT ''"
        )
    if "member" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN member TEXT NOT NULL DEFAULT 'Soban Khan'"
        )
    if "sync_id" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN sync_id TEXT DEFAULT NULL"
        )
    # Create the unique index on sync_id after ensuring the column exists.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_sync_id
        ON expenses (sync_id) WHERE sync_id IS NOT NULL
        """
    )
    connection.commit()


def add_expense(
    amount_cents,
    expense_date,
    category,
    notes,
    description="",
    member=None,
    sync_id=None,
):
    connection = get_db()
    cursor = connection.execute(
        """
        INSERT INTO expenses
            (amount_cents, expense_date, category, description, notes, member, sync_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            amount_cents,
            expense_date,
            category,
            description or "",
            notes or "",
            member or DEFAULT_MEMBER,
            sync_id,
        ),
    )
    connection.commit()
    return cursor.lastrowid


def get_expense(expense_id):
    row = get_db().execute(
        _SELECT_EXPENSES + " WHERE id = ?",
        (expense_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def get_expense_by_sync_id(sync_id):
    if not sync_id:
        return None
    row = get_db().execute(
        _SELECT_EXPENSES + " WHERE sync_id = ?",
        (sync_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def update_expense(
    expense_id,
    amount_cents,
    expense_date,
    category,
    notes,
    description=None,
    member=None,
):
    current = get_expense(expense_id)
    if current is None:
        return False

    new_description = (
        current["description"] if description is None else description
    )
    new_member = (
        current.get("member") or DEFAULT_MEMBER if member is None else member
    )

    cursor = get_db().execute(
        """
        UPDATE expenses
        SET amount_cents = ?, expense_date = ?, category = ?,
            notes = ?, description = ?, member = ?
        WHERE id = ?
        """,
        (
            amount_cents,
            expense_date,
            category,
            notes,
            new_description,
            new_member,
            expense_id,
        ),
    )
    get_db().commit()
    return cursor.rowcount > 0


def delete_expense(expense_id):
    cursor = get_db().execute(
        "DELETE FROM expenses WHERE id = ?",
        (expense_id,),
    )
    get_db().commit()
    return cursor.rowcount > 0


def get_expenses(limit=None, member=None):
    connection = get_db()
    conditions = []
    parameters = []
    if member:
        conditions.append("member = ?")
        parameters.append(member)
    query = _SELECT_EXPENSES
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY expense_date DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        parameters.append(limit)
    rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_expenses_for_date(expense_date):
    rows = get_db().execute(
        _SELECT_EXPENSES + " WHERE expense_date = ? ORDER BY id DESC",
        (expense_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_expenses_between(start_date, end_date):
    rows = get_db().execute(
        _SELECT_EXPENSES
        + " WHERE expense_date >= ? AND expense_date < ?"
        + " ORDER BY expense_date ASC, id ASC",
        (start_date, end_date),
    ).fetchall()
    return [dict(row) for row in rows]


def get_expense_totals():
    row = get_db().execute(
        """
        SELECT COUNT(*) AS expense_count,
               COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM expenses
        """
    ).fetchone()
    return dict(row)


def get_expense_totals_for_date(expense_date):
    row = get_db().execute(
        """
        SELECT COUNT(*) AS expense_count,
               COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM expenses
        WHERE expense_date = ?
        """,
        (expense_date,),
    ).fetchone()
    return dict(row)


def get_expense_totals_between(start_date, end_date):
    row = get_db().execute(
        """
        SELECT COUNT(*) AS expense_count,
               COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM expenses
        WHERE expense_date >= ? AND expense_date < ?
        """,
        (start_date, end_date),
    ).fetchone()
    return dict(row)


def get_expense_category_totals_between(start_date, end_date):
    rows = get_db().execute(
        """
        SELECT category,
               COUNT(*) AS expense_count,
               SUM(amount_cents) AS total_cents
        FROM expenses
        WHERE expense_date >= ? AND expense_date < ?
        GROUP BY category
        ORDER BY total_cents DESC, category COLLATE NOCASE
        """,
        (start_date, end_date),
    ).fetchall()
    return [dict(row) for row in rows]


def get_expense_member_totals_between(start_date, end_date):
    rows = get_db().execute(
        """
        SELECT COALESCE(NULLIF(TRIM(member), ''), ?) AS member,
               COUNT(*) AS expense_count,
               COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM expenses
        WHERE expense_date >= ? AND expense_date < ?
        GROUP BY member
        ORDER BY total_cents DESC, member COLLATE NOCASE
        """,
        (DEFAULT_MEMBER, start_date, end_date),
    ).fetchall()
    return [dict(row) for row in rows]


def get_expense_member_totals():
    rows = get_db().execute(
        """
        SELECT COALESCE(NULLIF(TRIM(member), ''), ?) AS member,
               COUNT(*) AS expense_count,
               COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM expenses
        GROUP BY member
        ORDER BY total_cents DESC, member COLLATE NOCASE
        """,
        (DEFAULT_MEMBER,),
    ).fetchall()
    return [dict(row) for row in rows]


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
