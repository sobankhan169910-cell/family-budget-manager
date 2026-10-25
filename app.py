import os
import secrets
import sqlite3
from datetime import date, timedelta
from io import BytesIO

from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from config import Config
from database import db
from services import data_export_service, expense_service, report_service


csrf = CSRFProtect()


def _validate_production_config(app, test_config=None):
    """Validate production-only settings and install the ProxyFix middleware.

    Raises RuntimeError when the production configuration is unsafe or
    incomplete, using the same messages as the original inline checks.
    """
    if app.config.get("APP_ENV") != "production":
        return

    persistent_directory = app.config.get("PERSISTENT_DATA_DIR")
    database_path = os.path.realpath(app.config["DATABASE"])
    backup_directory = os.path.realpath(app.config["BACKUP_DIRECTORY"])
    if not app.config.get("AUTH_REQUIRED"):
        raise RuntimeError("Authentication must be enabled in production.")
    if not app.config.get("SESSION_COOKIE_SECURE"):
        raise RuntimeError("Secure session cookies must be enabled in production.")
    if app.config.get("DEBUG"):
        raise RuntimeError("Flask debug mode must be disabled in production.")
    if not persistent_directory:
        raise RuntimeError("PERSISTENT_DATA_DIR must point to the mounted data disk.")
    persistent_root = os.path.realpath(persistent_directory)
    if (
        (test_config or {}).get("REQUIRE_PERSISTENT_MOUNT", True)
        and not os.path.ismount(persistent_root)
    ):
        raise RuntimeError("PERSISTENT_DATA_DIR is not a mounted persistent disk.")
    try:
        database_is_persistent = (
            os.path.commonpath((database_path, persistent_root)) == persistent_root
        )
        backups_are_persistent = (
            os.path.commonpath((backup_directory, persistent_root)) == persistent_root
        )
    except ValueError:
        database_is_persistent = False
        backups_are_persistent = False
    if not database_is_persistent or not backups_are_persistent:
        raise RuntimeError(
            "The database and backups must be inside PERSISTENT_DATA_DIR."
        )

    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
        x_port=1,
    )


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        if app.config.get("APP_ENV") == "production":
            raise RuntimeError("SECRET_KEY must be configured in production.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
    if not isinstance(app.config.get("PERMANENT_SESSION_LIFETIME"), timedelta):
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
            seconds=app.config["PERMANENT_SESSION_LIFETIME"]
        )

    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = Config.database_path(app.instance_path)
    if not app.config.get("BACKUP_DIRECTORY"):
        app.config["BACKUP_DIRECTORY"] = os.path.join(
            os.path.dirname(app.config["DATABASE"]),
            "backups",
        )

    if app.config.get("AUTH_REQUIRED"):
        if not app.config.get("APP_USERNAME") or not app.config.get("APP_PASSWORD_HASH"):
            raise RuntimeError(
                "APP_USERNAME and APP_PASSWORD_HASH are required when authentication is enabled."
            )
        try:
            check_password_hash(app.config["APP_PASSWORD_HASH"], "configuration-check")
        except ValueError as error:
            raise RuntimeError("APP_PASSWORD_HASH is not a valid Werkzeug password hash.") from error

    _validate_production_config(app, test_config)

    db.init_app(app)
    csrf.init_app(app)
    login_limiter = Limiter(
        get_remote_address,
        app=app,
        storage_uri="memory://",
        default_limits=[],
    )

    @app.before_request
    def require_login():
        if not current_app.config["AUTH_REQUIRED"]:
            return None
        if request.endpoint in {
            "login", "health_check", "service_worker",
            "static", "manifest_file",
        }:
            return None
        if session.get("authenticated"):
            return None
        return redirect(url_for("login"))

    @app.after_request
    def add_security_headers(response):
        if request.endpoint not in {"static", "service_worker", "manifest_file"}:
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'",
        )
        if request.is_secure and current_app.config["APP_ENV"] == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.get("/healthz")
    def health_check():
        db.get_db().execute("SELECT 1").fetchone()
        return {"status": "ok"}

    @app.route("/login", methods=["GET", "POST"])
    @login_limiter.limit("5 per minute")
    def login():
        if not current_app.config["AUTH_REQUIRED"]:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            username_is_valid = secrets.compare_digest(
                username,
                current_app.config["APP_USERNAME"],
            )
            password_is_valid = check_password_hash(
                current_app.config["APP_PASSWORD_HASH"],
                password,
            )
            if username_is_valid and password_is_valid:
                session.clear()
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            return render_template(
                "login.html",
                error="The username or password is incorrect.",
            ), 401
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/service-worker.js")
    def service_worker():
        response = send_from_directory(
            app.static_folder,
            "service-worker.js",
            mimetype="application/javascript",
            max_age=0,
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/manifest.webmanifest")
    def manifest_file():
        return send_from_directory(
            app.static_folder,
            "manifest.webmanifest",
            mimetype="application/manifest+json",
            max_age=86400,
        )

    @app.get("/")
    def dashboard():
        summary = report_service.get_dashboard_summary()
        try:
            monthly_report = report_service.get_monthly_report(
                request.args.get("month")
            )
        except ValueError:
            abort(400)
        recent_expenses = expense_service.get_recent_expenses()
        member_totals = report_service.get_member_totals()
        return render_template(
            "dashboard.html",
            summary=summary,
            monthly_report=monthly_report,
            expenses=recent_expenses,
            member_totals=member_totals,
            members=expense_service.MEMBERS,
        )

    @app.route("/expenses/add", methods=["GET", "POST"])
    def add_expense():
        if request.method == "POST":
            try:
                expense_service.add_expense(
                    amount=request.form.get("amount", ""),
                    expense_date=request.form.get("expense_date", ""),
                    category=request.form.get("category", ""),
                    custom_category=request.form.get("custom_category", ""),
                    notes=request.form.get("notes", ""),
                    member=request.form.get("member", "Soban Khan"),
                )
            except ValueError as error:
                return render_template(
                    "add_expense.html",
                    error=str(error),
                    form_data=request.form,
                    categories=expense_service.CATEGORIES,
                    members=expense_service.MEMBERS,
                ), 400
            return redirect(url_for("add_expense", saved="1"))

        return render_template(
            "add_expense.html",
            form_data={"expense_date": date.today().isoformat()},
            categories=expense_service.CATEGORIES,
            members=expense_service.MEMBERS,
            editing=False,
        )

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    def edit_expense(expense_id):
        expense = expense_service.get_expense(expense_id)
        if expense is None:
            abort(404)

        if request.method == "POST":
            try:
                updated = expense_service.update_expense(
                    expense_id=expense_id,
                    amount=request.form.get("amount", ""),
                    expense_date=request.form.get("expense_date", ""),
                    category=request.form.get("category", ""),
                    custom_category=request.form.get("custom_category", ""),
                    notes=request.form.get("notes", ""),
                    member=request.form.get("member", None),
                )
                if not updated:
                    abort(404)
            except ValueError as error:
                return render_template(
                    "add_expense.html",
                    editing=True,
                    expense=expense,
                    error=str(error),
                    form_data=request.form,
                    categories=expense_service.CATEGORIES,
                    members=expense_service.MEMBERS,
                ), 400

            return redirect(
                url_for(
                    "day_details",
                    expense_date=request.form.get("expense_date", ""),
                    updated=1,
                )
            )

        return render_template(
            "add_expense.html",
            editing=True,
            expense=expense,
            form_data={
                "amount": f"{expense['amount_cents'] / 100:.2f}",
                "expense_date": expense["expense_date"],
                "category": (
                    expense["category"]
                    if expense["category"] in expense_service.CATEGORIES
                    else "Other"
                ),
                "custom_category": (
                    expense["category"]
                    if expense["category"] not in expense_service.CATEGORIES
                    else ""
                ),
                "notes": expense["notes"],
                "member": expense.get("member", "Soban Khan"),
            },
            categories=expense_service.CATEGORIES,
            members=expense_service.MEMBERS,
        )

    @app.post("/expenses/<int:expense_id>/delete")
    def delete_expense(expense_id):
        if not expense_service.delete_expense(expense_id):
            abort(404)
        return redirect(url_for("history", deleted=1))

    @app.get("/expenses")
    def history():
        expenses = expense_service.get_expenses()
        return render_template("history.html", expenses=expenses)

    @app.get("/expenses/export")
    def export_expenses():
        selected_month = request.args.get("month")
        if selected_month:
            try:
                report = report_service.get_monthly_report(selected_month)
            except ValueError:
                abort(400)
            csv_content = data_export_service.create_expenses_csv(
                report["start_date"],
                report["end_date"],
            )
        else:
            selected_month = None
            csv_content = data_export_service.create_expenses_csv()

        filename = data_export_service.safe_export_filename(selected_month)
        response = send_file(
            BytesIO(csv_content.encode("utf-8")),
            mimetype="text/csv; charset=utf-8",
            as_attachment=True,
            download_name=filename,
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/expenses/backup")
    def backup_database():
        try:
            data_export_service.create_database_backup(
                current_app.config["DATABASE"],
                current_app.config["BACKUP_DIRECTORY"],
                current_app.static_folder,
            )
        except (OSError, sqlite3.Error, ValueError):
            current_app.logger.exception("Unable to create SQLite backup")
            return "Database backup could not be created.", 500
        return redirect(url_for("dashboard", backup="created"))

    @app.get("/expenses/day/<expense_date>")
    def day_details(expense_date):
        try:
            expenses = expense_service.get_expenses_for_date(expense_date)
        except ValueError:
            abort(404)
        summary = report_service.get_daily_summary(expense_date)
        return render_template(
            "day_details.html",
            expense_date=expense_date,
            expenses=expenses,
            summary=summary,
        )

    @app.get("/analytics")
    def analytics():
        try:
            monthly_report = report_service.get_monthly_report(
                request.args.get("month")
            )
        except ValueError:
            abort(400)
        member_totals = report_service.get_member_totals()
        summary = report_service.get_dashboard_summary()
        return render_template(
            "analytics.html",
            monthly_report=monthly_report,
            member_totals=member_totals,
            summary=summary,
            members=expense_service.MEMBERS,
        )

    @app.get("/settings")
    def settings():
        return render_template("settings.html")

    # ── JSON API for offline sync ──────────────────────────────────────
    @app.get("/api/expenses")
    def api_get_expenses():
        expenses = db.get_expenses()
        result = []
        for e in expenses:
            result.append({
                "id": e["id"],
                "amount_cents": e["amount_cents"],
                "category": e["category"],
                "description": e.get("description", ""),
                "notes": e.get("notes", ""),
                "member": e.get("member", "Soban Khan"),
                "sync_id": e.get("sync_id"),
                "expense_date": e["expense_date"],
                "created_at": e["created_at"],
            })
        return jsonify(result)

    @app.post("/api/expenses/sync")
    def api_sync_expenses():
        """Accept a batch of offline expense operations and apply them."""
        data = request.get_json(silent=True)
        if not data or not isinstance(data, list):
            return jsonify({"error": "Expected a JSON array of operations"}), 400

        results = []
        for op in data:
            action = op.get("action")
            sync_id = op.get("sync_id")
            try:
                if action == "add":
                    expense_id = db.add_expense(
                        amount_cents=int(op.get("amount_cents", 0)),
                        expense_date=op.get("expense_date", ""),
                        category=op.get("category", "Other"),
                        notes=op.get("notes", ""),
                        description=op.get("description", ""),
                        member=op.get("member", "Soban Khan"),
                        sync_id=sync_id,
                    )
                    results.append({
                        "sync_id": sync_id,
                        "server_id": expense_id,
                        "status": "created",
                    })
                elif action == "update":
                    existing = db.get_expense_by_sync_id(sync_id) if sync_id else None
                    target_id = existing["id"] if existing else op.get("server_id")
                    if target_id:
                        db.update_expense(
                            expense_id=int(target_id),
                            amount_cents=int(op.get("amount_cents", 0)),
                            expense_date=op.get("expense_date", ""),
                            category=op.get("category", "Other"),
                            notes=op.get("notes", ""),
                            description=op.get("description", ""),
                            member=op.get("member", "Soban Khan"),
                        )
                        results.append({
                            "sync_id": sync_id,
                            "server_id": target_id,
                            "status": "updated",
                        })
                    else:
                        results.append({
                            "sync_id": sync_id,
                            "status": "not_found",
                        })
                elif action == "delete":
                    existing = db.get_expense_by_sync_id(sync_id) if sync_id else None
                    target_id = existing["id"] if existing else op.get("server_id")
                    if target_id:
                        db.delete_expense(int(target_id))
                        results.append({
                            "sync_id": sync_id,
                            "server_id": target_id,
                            "status": "deleted",
                        })
                    else:
                        results.append({
                            "sync_id": sync_id,
                            "status": "already_deleted",
                        })
                else:
                    results.append({
                        "sync_id": sync_id,
                        "status": "unknown_action",
                    })
            except Exception as exc:
                current_app.logger.warning(
                    "Sync operation failed for sync_id=%s: %s", sync_id, exc
                )
                results.append({
                    "sync_id": sync_id,
                    "status": "error",
                    "message": str(exc),
                })

        return jsonify(results)

    @app.errorhandler(404)
    def not_found(error):
        del error
        return render_template("404.html"), 404

    @app.errorhandler(400)
    def bad_request(_error):
        del _error
        return render_template("400.html"), 400

    @app.errorhandler(429)
    def too_many_requests(_error):
        del _error
        return render_template("429.html"), 429

    @app.errorhandler(500)
    def internal_server_error(_error):
        current_app.logger.error(
            "An unexpected application error occurred (%s)",
            type(_error).__name__,
        )
        return render_template("500.html"), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
