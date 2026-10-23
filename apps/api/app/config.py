"""Runtime configuration from environment variables. See README "Configuration"."""

import os
import secrets
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = API_DIR.parent.parent
DATA_DIR = API_DIR / "data"

APP_ENV = os.getenv("APP_ENV", "development")  # development | staging | production
IS_DEV = APP_ENV == "development"


def _secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if APP_ENV == "production":
        raise RuntimeError("SECRET_KEY is required in production")
    # Development: generate once and keep it next to the database so encrypted data stays readable.
    path = DATA_DIR / ".dev_secret_key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48))
    return path.read_text().strip()


SECRET_KEY = _secret_key()
KMS_KEY_ID = os.getenv("KMS_KEY_ID")  # reserved; the app-level key is used until a KMS adapter exists

FILES_DIR = Path(os.getenv("FILES_DIR", DATA_DIR / "files"))
EXPORTS_DIR = Path(os.getenv("EXPORTS_DIR", DATA_DIR / "exports"))
RULES_DIR = REPO_DIR / "rules"
TEMPLATES_DIR = REPO_DIR / "templates"

MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "capture")  # capture | smtp | ses
MAIL_FROM = os.getenv("MAIL_FROM", "Unlink <no-reply@unlink.local>")
MAIL_RATE_PER_MINUTE = int(os.getenv("MAIL_RATE_PER_MINUTE", "20"))
SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("SES_SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT") or os.getenv("SES_SMTP_PORT") or "587")
SMTP_USER = os.getenv("SMTP_USER") or os.getenv("SES_SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") or os.getenv("SES_SMTP_PASSWORD")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() == "true"

RULESET_MODE = os.getenv("RULESET_MODE", "development")  # development | production
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:3100")
REDIS_URL = os.getenv("REDIS_URL")  # reserved; the database queue is used (see README)
CLAMD_SOCKET = os.getenv("CLAMD_SOCKET")  # optional ClamAV daemon for upload scanning

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
LOGIN_MAX_FAILURES_ACCOUNT = 5
LOGIN_MAX_FAILURES_IP = 20
LOGIN_WINDOW_MINUTES = 15

MFA_ROLES = {"legal", "finance", "approver", "admin"}


def live_mail_allowed() -> bool:
    """Real delivery only in staging/production with a non-capture provider configured."""
    return APP_ENV in ("staging", "production") and MAIL_PROVIDER != "capture"
