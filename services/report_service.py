from datetime import date, datetime

from database import db


def get_dashboard_summary():
    return db.get_expense_totals()


def get_current_month_summary(today=None):
    current_date = today or date.today()
    month_start = current_date.replace(day=1)
    if month_start.month == 12:
        next_month_start = month_start.replace(
            year=month_start.year + 1,
            month=1,
        )
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return db.get_expense_totals_between(
        month_start.isoformat(),
        next_month_start.isoformat(),
    )


def get_monthly_report(month=None, today=None):
    selected_month = month or (today or date.today()).strftime("%Y-%m")
    try:
        month_start = datetime.strptime(selected_month, "%Y-%m").date()
    except (TypeError, ValueError):
        raise ValueError("Select a valid month.") from None

    if month_start.strftime("%Y-%m") != selected_month:
        raise ValueError("Select a valid month.")

    if month_start.month == 12:
        try:
            next_month_start = month_start.replace(
                year=month_start.year + 1,
                month=1,
            )
        except ValueError:
            raise ValueError("Select a valid month.") from None
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)

    start_date = month_start.isoformat()
    end_date = next_month_start.isoformat()
    return {
        "month": selected_month,
        "month_label": month_start.strftime("%B %Y"),
        "start_date": start_date,
        "end_date": end_date,
        "total": db.get_expense_totals_between(start_date, end_date),
        "categories": db.get_expense_category_totals_between(
            start_date,
            end_date,
        ),
    }


def get_daily_summary(expense_date):
    return db.get_expense_totals_for_date(expense_date)
