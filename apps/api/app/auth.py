"""Passwords (scrypt), server-side sessions, login rate limiting, and TOTP multi-factor auth."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import (
    LOGIN_MAX_FAILURES_ACCOUNT,
    LOGIN_MAX_FAILURES_IP,
    LOGIN_WINDOW_MINUTES,
    MFA_ROLES,
)
from app.crypto import decrypt_str, encrypt_str
from app.models import AuthSession, EmployeeAccount, LoginAttempt, User, utcnow

SESSION_COOKIE = "unlink_session"
SESSION_TTL = timedelta(hours=12)
_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(candidate.hex(), digest)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- rate limiting

def too_many_failures(db: Session, account_key: str, ip: str | None) -> bool:
    since = utcnow() - timedelta(minutes=LOGIN_WINDOW_MINUTES)
    by_account = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.account_key == account_key, LoginAttempt.success.is_(False), LoginAttempt.created_at >= since))
    by_ip = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.ip == ip, LoginAttempt.success.is_(False), LoginAttempt.created_at >= since)) if ip else 0
    return by_account >= LOGIN_MAX_FAILURES_ACCOUNT or by_ip >= LOGIN_MAX_FAILURES_IP


def record_attempt(db: Session, account_key: str, ip: str | None, success: bool, org_id: int | None) -> None:
    db.add(LoginAttempt(account_key=account_key, ip=ip, success=success, org_id=org_id))
    if success:  # a successful login clears that account's failure streak
        db.execute(delete(LoginAttempt).where(LoginAttempt.account_key == account_key,
                                              LoginAttempt.success.is_(False)))


# ---------------------------------------------------------------- sessions

def create_session(db: Session, *, org_id: int, user: User | None = None,
                   employee_account: EmployeeAccount | None = None, ip: str | None = None) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    s = AuthSession(org_id=org_id, user_id=user.id if user else None,
                    employee_account_id=employee_account.id if employee_account else None,
                    token_hash=token_hash(token), ip=ip, mfa_verified=False,
                    expires_at=utcnow() + SESSION_TTL, last_seen_at=utcnow())
    db.add(s)
    db.flush()
    return token, s


def resolve_session(db: Session, token: str) -> AuthSession | None:
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    if s is None or aware(s.expires_at) < datetime.now(timezone.utc):
        return None
    if s.user_id:
        u = db.get(User, s.user_id)
        if not u or not u.active:
            return None
    elif s.employee_account_id:
        a = db.get(EmployeeAccount, s.employee_account_id)
        if not a or not a.active:
            return None
    else:
        return None
    return s


def end_session(db: Session, token: str) -> None:
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))


def end_all_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


# ---------------------------------------------------------------- MFA (TOTP)

def mfa_required(user: User) -> bool:
    return user.role in MFA_ROLES


def ensure_mfa_secret(user: User) -> str:
    """Return the user's TOTP secret, creating (but not enabling) one if needed."""
    if not user.mfa_secret_enc:
        user.mfa_secret_enc = encrypt_str(pyotp.random_base32())
    return decrypt_str(user.mfa_secret_enc)


def otpauth_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Unlink")


def verify_totp(user: User, code: str) -> bool:
    if not user.mfa_secret_enc:
        return False
    return pyotp.TOTP(decrypt_str(user.mfa_secret_enc)).verify(code.strip(), valid_window=1)


def current_totp(user: User) -> str:
    return pyotp.TOTP(ensure_mfa_secret(user)).now()
