import csv
import io
import os
import re
import sqlite3
import tempfile
import unittest

from app import create_app


class DataExportAndBackupTestCase(unittest.TestCase):
    PREDEFINED_CATEGORIES = {
        "School Fees",
        "Groceries",
        "Meat/Food",
        "Cow Expenses",
        "Bills",
        "Transport",
        "Medical",
        "Other",
    }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test.sqlite3")
        self.backup_directory = os.path.join(self.temp_dir.name, "private", "backups")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "BACKUP_DIRECTORY": self.backup_directory,
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_expense(self, amount, expense_date, category, notes=""):
        return self.client.post(
            "/expenses/add",
            data={
                "amount": amount,
                "expense_date": expense_date,
                "category": (
                    category
                    if category in self.PREDEFINED_CATEGORIES
                    else "Other"
                ),
                "custom_category": (
                    category
                    if category not in self.PREDEFINED_CATEGORIES
                    else ""
                ),
                "notes": notes,
            },
        )

    def parse_csv_response(self, response):
        return list(
            csv.DictReader(
                io.StringIO(response.data.decode("utf-8-sig"), newline="")
            )
        )

    def test_all_expense_csv_contains_existing_fields_custom_category_and_unicode(self):
        saved = self.add_expense(
            "123.45",
            "2026-10-09",
            "Électricité",
            "電気料金",
        )
        self.assertEqual(saved.status_code, 302)

        response = self.client.get("/expenses/export")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
        self.assertIn(
            'attachment; filename=family-expenses-all-'.encode(),
            response.headers["Content-Disposition"].encode(),
        )
        self.assertRegex(
            response.headers["Content-Disposition"],
            r'filename=family-expenses-all-\d{8}\.csv',
        )
        self.assertNotIn(self.temp_dir.name, response.headers["Content-Disposition"])
        self.assertEqual(
            set(self.parse_csv_response(response)[0]),
            {
                "id",
                "expense_date",
                "category",
                "amount_pkr",
                "description",
                "notes",
                "created_at",
            },
        )
        row = self.parse_csv_response(response)[0]
        self.assertEqual(row["expense_date"], "2026-10-09")
        self.assertEqual(row["category"], "Électricité")
        self.assertEqual(row["amount_pkr"], "123.45")
        self.assertEqual(row["notes"], "電気料金")
        self.assertEqual(row["description"], "")

    def test_month_csv_only_contains_expenses_in_selected_month(self):
        self.add_expense("10.00", "2026-10-09", "Groceries")
        self.add_expense("20.00", "2026-11-01", "School Fees")

        response = self.client.get("/expenses/export?month=2026-10")

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.headers["Content-Disposition"],
            r'filename=family-expenses-2026-10-\d{8}\.csv',
        )
        rows = self.parse_csv_response(response)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expense_date"], "2026-10-09")
        self.assertEqual(rows[0]["category"], "Groceries")

    def test_formula_like_text_fields_are_escaped(self):
        self.add_expense(
            "1.00",
            "2026-10-09",
            "=HYPERLINK",
            "=1+1",
        )
        with self.app.app_context():
            from database import db

            db.get_db().execute(
                "UPDATE expenses SET description = ?",
                ("=legacy formula value",),
            )
            db.get_db().commit()
        response = self.client.get("/expenses/export")

        self.assertEqual(response.status_code, 200)
        row = self.parse_csv_response(response)[0]
        self.assertEqual(row["category"], "'=HYPERLINK")
        self.assertEqual(row["notes"], "'=1+1")
        self.assertEqual(row["description"], "'=legacy formula value")

    def test_empty_csv_has_headers_and_safe_filename(self):
        response = self.client.get("/expenses/export?month=2020-02")

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.headers["Content-Disposition"],
            r'filename=family-expenses-2020-02-\d{8}\.csv',
        )
        rows = self.parse_csv_response(response)
        self.assertEqual(rows, [])
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))

    def test_invalid_month_export_is_rejected(self):
        response = self.client.get("/expenses/export?month=2026-99")

        self.assertEqual(response.status_code, 400)

    def test_backup_is_valid_sqlite_and_stored_outside_static_directory(self):
        self.add_expense("77.77", "2026-10-09", "Groceries")

        response = self.client.post("/expenses/backup")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(os.listdir(self.backup_directory)), 1)
        self.assertEqual(response.headers["Location"], "/?backup=created")
        backup_files = os.listdir(self.backup_directory)
        self.assertRegex(
            backup_files[0],
            r"^family-budget-backup-\d{8}-\d{6}-\d{6}-[0-9a-f]{8}\.sqlite3$",
        )
        backup_path = os.path.join(self.backup_directory, backup_files[0])
        self.assertNotIn(
            os.path.join("static", "images"),
            os.path.relpath(backup_path, self.temp_dir.name),
        )

        with sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True) as backup:
            tables = {
                row[0]
                for row in backup.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            count, cents = backup.execute(
                "SELECT COUNT(*), COALESCE(SUM(amount_cents), 0) FROM expenses"
            ).fetchone()
            integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]

        self.assertIn("expenses", tables)
        self.assertEqual((count, cents), (1, 7777))
        self.assertEqual(integrity, "ok")
        self.assertNotIn(backup_path, response.headers["Location"])

    def test_backup_refuses_public_static_directory(self):
        unsafe_app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": False,
            }
        )
        unsafe_backup_directory = os.path.join(
            unsafe_app.static_folder,
            "downloads",
        )
        unsafe_app.config["BACKUP_DIRECTORY"] = unsafe_backup_directory

        response = unsafe_app.test_client().post("/expenses/backup")

        self.assertEqual(response.status_code, 500)
        self.assertFalse(os.path.exists(unsafe_backup_directory))

    def test_repeated_backup_creates_unique_files_without_overwriting(self):
        first = self.client.post("/expenses/backup")
        second = self.client.post("/expenses/backup")

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(len(os.listdir(self.backup_directory)), 2)
        self.assertEqual(len(set(os.listdir(self.backup_directory))), 2)


if __name__ == "__main__":
    unittest.main()
