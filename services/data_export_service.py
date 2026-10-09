import csv
import io
import os
import re
import secrets
import sqlite3
from datetime import datetime

from database import db


CSV_FIELDS = (
    "id",
    "expense_date",
    "category",
    "amount_pkr",
    "description",
    "notes",
    "created_at",
)


def _spreadsheet_safe(value):
    if not isinstance(value, str):
        return value
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value
    return value


def create_expenses_csv(start_date=None, end_date=None):
    if start_date is None or end_date is None:
        expenses = db.get_expenses()
    else:
        expenses = db.get_expenses_between(start_date, end_date)

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for expense in expenses:
        writer.writerow(
            {
                "id": expense["id"],
                "expense_date": _spreadsheet_safe(expense["expense_date"]),
                "category": _spreadsheet_safe(expense["category"]),
                "amount_pkr": (
                    f"{expense['amount_cents'] // 100}."
                    f"{expense['amount_cents'] % 100:02d}"
                ),
                "description": _spreadsheet_safe(expense["description"]),
                "notes": _spreadsheet_safe(expense["notes"]),
                "created_at": _spreadsheet_safe(expense["created_at"]),
            }
        )
    return "\ufeff" + output.getvalue()


def create_database_backup(database_path, backup_directory, public_directory):
    backup_root = os.path.normcase(os.path.realpath(backup_directory))
    public_root = os.path.normcase(os.path.realpath(public_directory))
    try:
        inside_public_directory = os.path.commonpath(
            (backup_root, public_root)
        ) == public_root
    except ValueError:
        inside_public_directory = False
    if inside_public_directory:
        raise ValueError("Database backups cannot be stored in the public directory.")

    os.makedirs(backup_directory, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"family-budget-backup-{timestamp}-{secrets.token_hex(4)}.sqlite3"
    backup_path = os.path.join(backup_directory, filename)
    descriptor = os.open(
        backup_path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)

    source = None
    destination = None
    completed = False
    try:
        source = sqlite3.connect(database_path)
        destination = sqlite3.connect(backup_path)
        source.backup(destination)
        destination.commit()
        completed = True
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        if not completed:
            try:
                os.remove(backup_path)
            except FileNotFoundError:
                pass

    return filename


def safe_export_filename(month=None, now=None):
    date_suffix = (now or datetime.now()).strftime("%Y%m%d")
    if month is None:
        suffix = "all"
    else:
        if re.fullmatch(r"\d{4}-\d{2}", month) is None:
            raise ValueError("Select a valid month.")
        suffix = month
    return f"family-expenses-{suffix}-{date_suffix}.csv"
