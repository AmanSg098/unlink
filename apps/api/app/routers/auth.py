from datetime import datetime, timezone

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    aware,
    create_session,
    current_totp,
    end_session,
    ensure_mfa_secret,
    hash_password,
    mfa_required,
    otpauth_uri,
    record_attempt,
    resolve_session,
    token_hash,
    too_many_failures,
    verify_password,
    verify_totp,
)
from app.config import IS_DEV
from app.db import get_db
from app.deps import Ctx, client_ip, get_any_ctx
from app.models import AuthSession, Employee, EmployeeAccount, Org, User
from app.schemas import ActivateIn, LoginIn, MePatch, MfaIn

router = APIRouter(tags=["auth"])

# Hash compared against when the email is unknown, so timing doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def _me(db: Session, ctx: Ctx) -> dict:
    org = db.get(Org, ctx.org_id)
    s = db.get(AuthSession, ctx.session_id)
    if ctx.kind == "employee":
        e = db.get(Employee, ctx.employee_id)
        return {"kind": "employee", "id": ctx.employee_id, "email": ctx.user, "full_name": e.full_name,
                "role": "employee", "org_id": org.id, "org_name": org.name, "employee_code": e.employee_code,
                "mfa_required": False, "mfa_verified": True, "mfa_enabled": False}
    u = db.get(User, ctx.user_id)
    return {"kind": "staff", "id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
            "org_id": org.id, "org_name": org.name, "employee_code": u.employee_code,
            "mfa_required": mfa_required(u), "mfa_verified": bool(s and s.mfa_verified), "mfa_enabled": u.mfa_enabled,
            "notify_email": u.notify_email}


def _qr_svg(uri: str) -> str:
    return qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).to_string(encoding="unicode")


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax",
                        max_age=int(SESSION_TTL.total_seconds()), path="/")


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    key = body.email.strip().lower()
    if too_many_failures(db, key, ip):
        raise HTTPException(429, "Too many failed sign-in attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == key))
    account = None if user else db.scalar(select(EmployeeAccount).where(func.lower(EmployeeAccount.email) == key))
    stored = user.password_hash if user else (account.password_hash if account else _DUMMY_HASH)
    ok = verify_password(body.password, stored) and bool((user and user.active) or (account and account.active))
    org_id = user.org_id if user else (account.org_id if account else None)
    record_attempt(db, key, ip, ok, org_id)
    if not ok:
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token, s = create_session(db, org_id=org_id, user=user, employee_account=account, ip=ip)
    actor = user.email if user else f"employee:{db.get(Employee, account.employee_id).employee_code}"
    audit.record_raw(db, org_id, actor, "session", s.id, "sign_in", None, {"kind": "staff" if user else "employee"})
    out: dict = {"mfa_required": False}
    if user and mfa_required(user):
        out["mfa_required"] = True
        out["mfa_enrolled"] = user.mfa_enabled
        if not user.mfa_enabled:
            uri = otpauth_uri(user, ensure_mfa_secret(user))
            out |= {"otpauth_uri": uri, "secret": uri.split("secret=")[1].split("&")[0], "qr_svg": _qr_svg(uri)}
    db.commit()
    _set_cookie(response, token)
    return out


@router.post("/auth/mfa/verify")
def mfa_verify(body: MfaIn, request: Request, ctx: Ctx = Depends(get_any_ctx), db: Session = Depends(get_db)):
    if ctx.kind != "staff":
        raise HTTPException(400, "Not required")
    u = db.get(User, ctx.user_id)
    key = f"mfa:{u.email}"
    ip = client_ip(request)
    if too_many_failures(db, key, ip):
        raise HTTPException(429, "Too many failed codes. Try again in 15 minutes.")
    ok = verify_totp(u, body.code)
    record_attempt(db, key, ip, ok, u.org_id)
    if not ok:
        db.commit()
        raise HTTPException(401, "That code didn't match. Check your authenticator app's clock and try again.")
    s = db.get(AuthSession, ctx.session_id)
    s.mfa_verified = True
    if not u.mfa_enabled:
        u.mfa_enabled = True
        audit.record(db, ctx, "user", u.id, "mfa_enrolled", None, {"mfa_enabled": True})
    audit.record(db, ctx, "session", s.id, "mfa_verified", None, None)
    db.commit()
    return _me(db, ctx)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db),
           token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    if token:
        s = resolve_session(db, token)
        if s:
            actor = db.get(User, s.user_id).email if s.user_id else "employee"
            audit.record_raw(db, s.org_id, actor, "session", s.id, "sign_out")
        end_session(db, token)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/auth/me")
def me(ctx: Ctx = Depends(get_any_ctx), db: Session = Depends(get_db)):
    out = _me(db, ctx)
    db.commit()
    return out


@router.patch("/auth/me")
def update_me(body: MePatch, ctx: Ctx = Depends(get_any_ctx), db: Session = Depends(get_db)):
    if ctx.kind != "staff":
        raise HTTPException(403, "Staff only")
    u = db.get(User, ctx.user_id)
    if body.notify_email is not None:
        u.notify_email = body.notify_email
    db.commit()
    return _me(db, ctx)


@router.get("/auth/sessions")
def my_sessions(ctx: Ctx = Depends(get_any_ctx), db: Session = Depends(get_db)):
    col = AuthSession.user_id if ctx.kind == "staff" else AuthSession.employee_account_id
    who = ctx.user_id if ctx.kind == "staff" else db.scalar(
        select(EmployeeAccount.id).where(EmployeeAccount.employee_id == ctx.employee_id))
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(AuthSession).where(col == who).order_by(AuthSession.id.desc())).all()
    return [{"id": s.id, "ip": s.ip, "created_at": s.created_at, "last_seen_at": s.last_seen_at,
             "current": s.id == ctx.session_id, "mfa_verified": s.mfa_verified}
            for s in rows if aware(s.expires_at) > now]


@router.delete("/auth/sessions/{session_id}", status_code=204)
def end_my_session(session_id: int, ctx: Ctx = Depends(get_any_ctx), db: Session = Depends(get_db)):
    s = db.get(AuthSession, session_id)
    mine = s and ((ctx.kind == "staff" and s.user_id == ctx.user_id) or
                  (ctx.kind == "employee" and s.employee_account_id is not None and
                   db.get(EmployeeAccount, s.employee_account_id).employee_id == ctx.employee_id))
    if not mine:
        raise HTTPException(404, "Session not found")
    db.delete(s)
    audit.record(db, ctx, "session", session_id, "end_session")
    db.commit()


@router.post("/auth/activate")
def activate(body: ActivateIn, db: Session = Depends(get_db)):
    """Employee self-service: set a password from an invite link."""
    a = db.scalar(select(EmployeeAccount).where(EmployeeAccount.invite_token_hash == token_hash(body.token)))
    if a is None or a.invite_expires_at is None or aware(a.invite_expires_at) < datetime.now(timezone.utc):
        raise HTTPException(400, "This invitation link is invalid or has expired. Ask HR for a new one.")
    a.password_hash, a.active, a.invite_token_hash, a.invite_expires_at = hash_password(body.password), True, None, None
    e = db.get(Employee, a.employee_id)
    audit.record_raw(db, a.org_id, f"employee:{e.employee_code}", "employee_account", a.id, "activate")
    db.commit()
    return {"email": a.email}


@router.get("/dev/totp")
def dev_totp(email: str, db: Session = Depends(get_db)):
    """Development only: current TOTP code for a demo account, so sign-in can be tested without a phone."""
    if not IS_DEV:
        raise HTTPException(404)
    u = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if u is None:
        raise HTTPException(404)
    code = current_totp(u)
    db.commit()
    return {"code": code, "warning": "Development only. This endpoint does not exist outside APP_ENV=development."}
