import os


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
    DEBUG = _environment_flag("FLASK_DEBUG")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    AUTH_REQUIRED = _environment_flag(
        "AUTH_REQUIRED",
        default=APP_ENV == "production",
    )
    APP_USERNAME = os.environ.get("APP_USERNAME", "")
    APP_PASSWORD_HASH = os.environ.get("APP_PASSWORD_HASH", "")
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    DATABASE = os.environ.get("DATABASE_PATH")
    BACKUP_DIRECTORY = os.environ.get("BACKUP_DIRECTORY")
    PERSISTENT_DATA_DIR = os.environ.get("PERSISTENT_DATA_DIR")

    @staticmethod
    def database_path(instance_path: str) -> str:
        return os.path.join(instance_path, "family_budget.sqlite3")
