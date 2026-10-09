import os
import re
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app


class ExpenseRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dashboard_loads_with_empty_database(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No expenses yet", response.data)

    def test_add_expense_form_defaults_to_today_and_lists_categories(self):
        response = self.client.get("/expenses/add")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'value="{date.today().isoformat()}"'.encode(),
            response.data,
        )
        for category in (
            b"School Fees",
            b"Groceries",
            b"Meat/Food",
            b"Cow Expenses",
            b"Bills",
            b"Transport",
            b"Medical",
            b"Other",
        ):
            self.assertIn(category, response.data)
        self.assertIn(b'id="custom_category"', response.data)
        self.assertNotIn(b'id="description"', response.data)

    def test_valid_expense_is_saved_and_shown(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "12.34",
                "expense_date": "2026-10-08",
                "category": "Groceries",
                "notes": "Weekly food shopping",
            },
        )
        success_page = self.client.get(response.headers["Location"])
        history_response = self.client.get("/expenses")
        day_response = self.client.get("/expenses/day/2026-10-08")
        dashboard_response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/expenses/add?saved=1")
        self.assertIn(b"Expense recorded successfully", success_page.data)
        self.assertEqual(history_response.status_code, 200)
        self.assertIn(b"2026-10-08", history_response.data)
        self.assertIn(b"Groceries", history_response.data)
        self.assertIn(b"PKR 12.34", history_response.data)
        self.assertIn(b"Weekly food shopping", day_response.data)
        self.assertIn(b"PKR 12.34", dashboard_response.data)
        self.assertIn(b"Expenses recorded", dashboard_response.data)

    def test_dashboard_selected_month_separates_two_months_from_all_time(self):
        current_date = date.today()
        previous_month_date = current_date.replace(day=1) - timedelta(days=1)
        for amount, expense_date, category, custom_category in (
            ("20.00", current_date.isoformat(), "Groceries", ""),
            ("10.00", previous_month_date.isoformat(), "Other", "Internet"),
        ):
            self.client.post(
                "/expenses/add",
                data={
                    "amount": amount,
                    "expense_date": expense_date,
                    "category": category,
                    "custom_category": custom_category,
                },
            )

        current_month = current_date.strftime("%Y-%m")
        previous_month = previous_month_date.strftime("%Y-%m")
        current_response = self.client.get(f"/?month={current_month}")
        previous_response = self.client.get(f"/?month={previous_month}")
        current_category_section = re.search(
            rb'<section class="content-card monthly-report-card">(.*?)</section>',
            current_response.data,
            re.DOTALL,
        ).group(1)
        previous_category_section = re.search(
            rb'<section class="content-card monthly-report-card">(.*?)</section>',
            previous_response.data,
            re.DOTALL,
        ).group(1)
        current_month_total = re.search(
            rb'<p class="muted">Spending in [^<]+</p>\s*'
            rb'<p class="summary-value">(PKR [0-9.]+)</p>',
            current_response.data,
        ).group(1)
        previous_month_total = re.search(
            rb'<p class="muted">Spending in [^<]+</p>\s*'
            rb'<p class="summary-value">(PKR [0-9.]+)</p>',
            previous_response.data,
        ).group(1)

        self.assertEqual(current_response.status_code, 200)
        self.assertIn(b"All-Time Total", current_response.data)
        self.assertIn(b"PKR 30.00", current_response.data)
        self.assertIn(
            current_date.strftime("%B %Y").encode(),
            current_response.data,
        )
        self.assertEqual(current_month_total, b"PKR 20.00")
        self.assertIn(b"Groceries", current_category_section)
        self.assertNotIn(b"Internet", current_category_section)

        self.assertEqual(previous_response.status_code, 200)
        self.assertIn(b"PKR 30.00", previous_response.data)
        previous_month_date_label = date(
            previous_month_date.year,
            previous_month_date.month,
            1,
        ).strftime("%B %Y")
        self.assertIn(previous_month_date_label.encode(), previous_response.data)
        self.assertEqual(previous_month_total, b"PKR 10.00")
        self.assertIn(b"Internet", previous_category_section)
        self.assertNotIn(b"Groceries", previous_category_section)

    def test_dashboard_selected_empty_month_shows_zero_and_empty_state(self):
        response = self.client.get("/?month=2020-02")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PKR 0.00", response.data)
        self.assertIn(b"No expenses recorded for February 2020", response.data)

    def test_dashboard_rejects_invalid_month_selector_value(self):
        response = self.client.get("/?month=2026-13")

        self.assertEqual(response.status_code, 400)

    def test_non_positive_amount_is_rejected(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "expense_date": "2026-10-09",
                "category": "Groceries",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"must be greater than zero", response.data)

    def test_amount_with_more_than_two_decimal_places_is_rejected(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "1.234",
                "expense_date": "2026-10-09",
                "category": "Groceries",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"no more than two digits", response.data)

    def test_invalid_date_is_rejected(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "expense_date": "2026-02-30",
                "category": "Groceries",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid date", response.data)

    def test_invalid_category_is_rejected(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "expense_date": "2026-10-09",
                "category": "Unlisted category",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid expense category", response.data)

    def test_empty_custom_category_is_rejected(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "expense_date": "2026-10-09",
                "category": "Other",
                "custom_category": "   ",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"custom category", response.data)

    def test_custom_category_is_trimmed_and_saved(self):
        response = self.client.post(
            "/expenses/add",
            data={
                "amount": "49.99",
                "expense_date": "2026-10-09",
                "category": "Other",
                "custom_category": "  Internet  ",
            },
        )

        self.assertEqual(response.status_code, 302)
        history = self.client.get("/expenses")
        self.assertIn(b"Internet", history.data)
        self.assertIn(b"PKR 49.99", history.data)
        daily = self.client.get("/expenses/day/2026-10-09")
        self.assertIn(b"Internet", daily.data)

    def test_custom_category_is_required_only_for_other(self):
        regular_category = self.client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "expense_date": "2026-10-09",
                "category": "Groceries",
            },
        )
        other_without_category_name = self.client.post(
            "/expenses/add",
            data={
                "amount": "10.00",
                "expense_date": "2026-10-09",
                "category": "Other",
            },
        )

        self.assertEqual(regular_category.status_code, 302)
        self.assertEqual(other_without_category_name.status_code, 400)

    def test_edit_shows_existing_custom_category_and_allows_saving_it(self):
        self.client.post(
            "/expenses/add",
            data={
                "amount": "22.00",
                "expense_date": "2026-10-09",
                "category": "Other",
                "custom_category": "Internet",
            },
        )
        history = self.client.get("/expenses")
        edit_match = re.search(rb'href="(/expenses/\d+/edit)"', history.data)
        self.assertIsNotNone(edit_match)
        edit_url = edit_match.group(1).decode()

        edit_page = self.client.get(edit_url)

        self.assertEqual(edit_page.status_code, 200)
        self.assertNotIn(b'id="description"', edit_page.data)
        self.assertRegex(
            edit_page.data,
            rb'<option value="Other"\s+selected>',
        )
        self.assertIn(b'value="Internet"', edit_page.data)
        self.assertIn(b'id="custom_category" name="custom_category"', edit_page.data)
        self.assertIn(b'custom_category" type="text"', edit_page.data)

        saved = self.client.post(
            edit_url,
            data={
                "amount": "24.00",
                "expense_date": "2026-10-09",
                "category": "Other",
                "custom_category": "Internet",
            },
        )

        self.assertEqual(saved.status_code, 302)
        self.assertIn(b"Internet", self.client.get("/expenses").data)

    def test_edit_preserves_existing_legacy_description_data(self):
        with self.app.app_context():
            from database import db

            cursor = db.get_db().execute(
                """
                INSERT INTO expenses
                    (amount_cents, expense_date, category, description, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (1000, "2026-10-09", "School Fees", "Legacy detail", ""),
            )
            db.get_db().commit()
            expense_id = cursor.lastrowid

        response = self.client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "15.00",
                "expense_date": "2026-10-09",
                "category": "Groceries",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        with sqlite3.connect(self.database_path) as connection:
            stored_description = connection.execute(
                "SELECT description FROM expenses WHERE id = ?",
                (expense_id,),
            ).fetchone()[0]
        self.assertEqual(stored_description, "Legacy detail")

    def test_each_missing_required_field_is_rejected(self):
        valid_fields = {
            "amount": "10.00",
            "expense_date": "2026-10-08",
            "category": "Groceries",
        }

        for missing_field in valid_fields:
            with self.subTest(missing_field=missing_field):
                form_data = valid_fields.copy()
                del form_data[missing_field]

                response = self.client.post("/expenses/add", data=form_data)

                self.assertEqual(response.status_code, 400)

    def test_expense_remains_available_after_app_restarts(self):
        self.client.post(
            "/expenses/add",
            data={
                "amount": "2500.50",
                "expense_date": "2026-10-09",
                "category": "School Fees",
                "notes": "Paid at school office",
            },
        )

        restarted_app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": False,
            }
        )
        response = restarted_app.test_client().get("/expenses")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"School Fees", response.data)
        self.assertIn(b"PKR 2500.50", response.data)

    def test_invalid_day_details_returns_not_found(self):
        response = self.client.get("/expenses/day/not-a-date")

        self.assertEqual(response.status_code, 404)
        self.assertIn(b"couldn't find that page", response.data)

    def test_day_details_shows_database_total_count_and_all_expenses(self):
        for amount in ("10.25", "4.75"):
            response = self.client.post(
                "/expenses/add",
                data={
                    "amount": amount,
                    "expense_date": "2026-10-08",
                    "category": "Groceries",
                },
            )
            self.assertEqual(response.status_code, 302)

        response = self.client.get("/expenses/day/2026-10-08")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PKR 15.00", response.data)
        self.assertIn(b">2</p>", response.data)
        self.assertIn(b"PKR 10.25", response.data)
        self.assertIn(b"PKR 4.75", response.data)
        self.assertIn(b">Edit</a>", response.data)
        self.assertIn(b">Delete</button>", response.data)
        self.assertIn(b'method="post"', response.data)

    def test_edit_updates_expense_and_recalculates_dashboard_and_daily_totals(self):
        current_date = date.today()
        previous_month_date = current_date.replace(day=1) - timedelta(days=1)
        self.client.post(
            "/expenses/add",
            data={
                "amount": "1000.00",
                "expense_date": current_date.isoformat(),
                "category": "School Fees",
            },
        )
        history_response = self.client.get("/expenses")
        edit_match = re.search(rb'href="(/expenses/\d+/edit)"', history_response.data)
        self.assertIsNotNone(edit_match)
        edit_url = edit_match.group(1).decode()

        edit_page = self.client.get(edit_url)
        self.assertEqual(edit_page.status_code, 200)
        self.assertIn(b'value="1000.00"', edit_page.data)

        updated = self.client.post(
            edit_url,
            data={
                "amount": "12.50",
                "expense_date": previous_month_date.isoformat(),
                "category": "Other",
                "custom_category": "Internet",
                "notes": "Updated notes",
            },
        )
        dashboard = self.client.get("/")
        old_day = self.client.get(
            f"/expenses/day/{current_date.isoformat()}"
        )
        new_day = self.client.get(updated.headers["Location"])

        self.assertEqual(updated.status_code, 302)
        self.assertEqual(
            updated.headers["Location"],
            f"/expenses/day/{previous_month_date.isoformat()}?updated=1",
        )
        self.assertIn(b"PKR 12.50", dashboard.data)
        self.assertIn(b"All-Time Total", dashboard.data)
        self.assertIn(b"PKR 0.00", dashboard.data)
        self.assertIn(b">1</p>", dashboard.data)
        self.assertIn(b"Expense updated successfully", new_day.data)
        self.assertIn(b"PKR 12.50", new_day.data)
        self.assertIn(b">1</p>", new_day.data)
        self.assertIn(b"Internet", new_day.data)
        self.assertIn(b"Updated notes", new_day.data)
        self.assertIn(b"PKR 0.00", old_day.data)
        self.assertIn(b">0</p>", old_day.data)

    def test_invalid_edit_does_not_change_saved_expense(self):
        self.client.post(
            "/expenses/add",
            data={
                "amount": "25.00",
                "expense_date": "2026-10-08",
                "category": "Groceries",
            },
        )
        expense = self.app.test_client().get("/expenses")
        edit_match = re.search(rb'href="(/expenses/\d+/edit)"', expense.data)
        self.assertIsNotNone(edit_match)
        edit_url = edit_match.group(1).decode()
        response = self.client.post(
            edit_url,
            data={
                "amount": "0",
                "expense_date": "2026-10-08",
                "category": "Groceries",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"must be greater than zero", response.data)
        self.assertIn(b"PKR 25.00", self.client.get("/expenses").data)

    def test_delete_requires_post_and_recalculates_totals(self):
        expense_date = date.today().isoformat()
        self.client.post(
            "/expenses/add",
            data={
                "amount": "30.00",
                "expense_date": expense_date,
                "category": "Groceries",
            },
        )
        history = self.client.get("/expenses")
        self.assertIn(b'data-confirm="Delete this expense?', history.data)
        delete_match = re.search(
            rb'<form class="delete-form" method="post" action="([^"]+)"',
            history.data,
        )
        self.assertIsNotNone(delete_match)
        delete_url = delete_match.group(1).decode()

        get_response = self.client.get(delete_url)
        self.assertEqual(get_response.status_code, 405)

        deleted = self.client.post(delete_url)
        dashboard = self.client.get("/")
        day = self.client.get(f"/expenses/day/{expense_date}")
        refreshed_history = self.client.get(deleted.headers["Location"])

        self.assertEqual(deleted.status_code, 302)
        self.assertEqual(deleted.headers["Location"], "/expenses?deleted=1")
        self.assertIn(b"PKR 0.00", dashboard.data)
        self.assertIn(b"All-Time Total", dashboard.data)
        self.assertIn(b">0</p>", dashboard.data)
        self.assertIn(b">0</p>", day.data)
        self.assertIn(b"Expense deleted successfully", refreshed_history.data)

    def test_edit_and_delete_nonexistent_expenses_return_not_found(self):
        self.assertEqual(self.client.get("/expenses/999/edit").status_code, 404)
        self.assertEqual(self.client.post("/expenses/999/delete").status_code, 404)


class ExistingDatabaseMigrationTestCase(unittest.TestCase):
    def test_existing_expense_is_preserved_when_new_columns_are_added(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = os.path.join(temp_dir, "existing.sqlite3")
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                    description TEXT NOT NULL DEFAULT '',
                    expense_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO expenses (amount_cents, description, expense_date)
                VALUES (5500, 'Existing expense', '2026-10-08');
                """
            )
            connection.commit()
            connection.close()

            migrated_app = create_app(
                {
                    "TESTING": True,
                    "DATABASE": database_path,
                    "AUTH_REQUIRED": False,
                    "WTF_CSRF_ENABLED": False,
                }
            )
            response = migrated_app.test_client().get("/expenses")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Existing expense", response.data)
        self.assertIn(b"Other", response.data)
        self.assertIn(b"PKR 55.00", response.data)


if __name__ == "__main__":
    unittest.main()
