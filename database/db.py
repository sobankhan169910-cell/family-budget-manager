import os
import sqlite3

from flask import current_app, g


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
    if "category" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'"
        )
    if "notes" not in existing_columns:
        connection.execute(
            "ALTER TABLE expenses ADD COLUMN notes TEXT NOT NULL DEFAULT ''"
        )
    connection.commit()


def add_expense(amount_cents, expense_date, category, notes):
    connection = get_db()
    cursor = connection.execute(
        """
        INSERT INTO expenses
            (amount_cents, expense_date, category, description, notes)
        VALUES (?, ?, ?, '', ?)
        """,
        (amount_cents, expense_date, category, notes),
    )
    connection.commit()
    return cursor.lastrowid


def get_expense(expense_id):
    row = get_db().execute(
        """
        SELECT id, amount_cents, category, description, notes,
               expense_date, created_at
        FROM expenses
        WHERE id = ?
        """,
        (expense_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def update_expense(expense_id, amount_cents, expense_date, category, notes):
    cursor = get_db().execute(
        """
        UPDATE expenses
        SET amount_cents = ?, expense_date = ?, category = ?,
            notes = ?
        WHERE id = ?
        """,
        (amount_cents, expense_date, category, notes, expense_id),
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


def get_expenses(limit=None):
    connection = get_db()
    if limit is None:
        rows = connection.execute(
            """
            SELECT id, amount_cents, category, description, notes,
                   expense_date, created_at
            FROM expenses
            ORDER BY expense_date DESC, id DESC
            """
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, amount_cents, category, description, notes,
                   expense_date, created_at
            FROM expenses
            ORDER BY expense_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_expenses_for_date(expense_date):
    rows = get_db().execute(
        """
        SELECT id, amount_cents, category, description, notes,
               expense_date, created_at
        FROM expenses
        WHERE expense_date = ?
        ORDER BY id DESC
        """,
        (expense_date,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_expenses_between(start_date, end_date):
    rows = get_db().execute(
        """
        SELECT id, expense_date, category, amount_cents,
               description, notes, created_at
        FROM expenses
        WHERE expense_date >= ? AND expense_date < ?
        ORDER BY expense_date ASC, id ASC
        """,
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


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
