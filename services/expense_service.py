from datetime import date
from decimal import Decimal, InvalidOperation

from database import db


CATEGORIES = (
    "School Fees",
    "Groceries",
    "Meat/Food",
    "Cow Expenses",
    "Bills",
    "Transport",
    "Medical",
    "Other",
)


def _parse_amount_cents(amount):
    try:
        value = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid expense amount.") from None

    if not value.is_finite() or value <= 0:
        raise ValueError("The expense amount must be greater than zero.")
    if value.as_tuple().exponent < -2:
        raise ValueError("Enter no more than two digits after the decimal point.")

    amount_cents = int(value * 100)
    if amount_cents > 999_999_999_99:
        raise ValueError("The expense amount is too large.")
    return amount_cents


def _parse_expense_date(expense_date):
    try:
        parsed_date = date.fromisoformat(str(expense_date).strip())
    except (TypeError, ValueError):
        raise ValueError("Enter a valid date in YYYY-MM-DD format.") from None

    if parsed_date.isoformat() != str(expense_date).strip():
        raise ValueError("Enter a valid date in YYYY-MM-DD format.")
    return parsed_date.isoformat()


def add_expense(amount, expense_date, category, custom_category="", notes=""):
    fields = _validate_expense_fields(
        amount, expense_date, category, custom_category, notes
    )
    return db.add_expense(*fields)


def _validate_expense_fields(
    amount, expense_date, category, custom_category, notes
):
    amount_cents = _parse_amount_cents(amount)
    validated_date = _parse_expense_date(expense_date)
    clean_category = str(category).strip()
    if clean_category not in CATEGORIES:
        raise ValueError("Choose a valid expense category.")
    if clean_category == "Other":
        clean_category = str(custom_category).strip()
        if not clean_category:
            raise ValueError("Enter a name for the custom category.")
        if len(clean_category) > 80:
            raise ValueError("Custom category must be 80 characters or fewer.")

    clean_notes = str(notes).strip()
    if len(clean_notes) > 2000:
        raise ValueError("Notes must be 2,000 characters or fewer.")

    return (
        amount_cents,
        validated_date,
        clean_category,
        clean_notes,
    )


def get_expense(expense_id):
    return db.get_expense(expense_id)


def update_expense(
    expense_id, amount, expense_date, category, custom_category="", notes=""
):
    fields = _validate_expense_fields(
        amount, expense_date, category, custom_category, notes
    )
    return db.update_expense(expense_id, *fields)


def delete_expense(expense_id):
    return db.delete_expense(expense_id)


def get_recent_expenses():
    return db.get_expenses(limit=5)


def get_expenses():
    return db.get_expenses()


def get_expenses_for_date(expense_date):
    validated_date = _parse_expense_date(expense_date)
    return db.get_expenses_for_date(validated_date)
