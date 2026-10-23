"""Request context: who is calling, from which organisation, with which role, and what they may see."""

from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, mfa_required, resolve_session
from app.db import get_db
from app.models import AuthSession, Employee, EmployeeAccount, User, utcnow

STAFF_ROLES = ("admin", "hr", "manager", "legal", "finance", "approver", "viewer")


@dataclass(frozen=True)
class Ctx:
    org_id: int
    user_id: int | None
    user: str  # email; recorded as the actor in the audit log
    role: str
    kind: str = "staff"  # staff | employee
    employee_id: int | None = None  # employee kind: own record; staff: linked record (managers)
    employee_code: str | None = None
    session_id: int | None = None
    ip: str | None = None
    team: frozenset[str] = field(default_factory=frozenset)  # manager: employee codes in reporting line

    def has(self, *roles: str) -> bool:
        return self.kind == "staff" and (self.role == "admin" or self.role in roles)


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)


def _token(cookie: str | None, authorization: str | None) -> str | None:
    if cookie:
        return cookie
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:]
    return None


def reporting_line(db: Session, org_id: int, manager_code: str | None) -> frozenset[str]:
    """All employee codes under a manager, direct and indirect."""
    if not manager_code:
        return frozenset()
    rows = db.execute(select(Employee.employee_code, Employee.manager_code).where(Employee.org_id == org_id)).all()
    children: dict[str, list[str]] = {}
    for code, mgr in rows:
        if mgr:
            children.setdefault(mgr, []).append(code)
    out, stack = set(), [manager_code]
    while stack:
        for c in children.get(stack.pop(), []):
            if c not in out:
                out.add(c)
                stack.append(c)
    return frozenset(out)


def _session(db: Session, cookie: str | None, authorization: str | None) -> AuthSession:
    token = _token(cookie, authorization)
    s = resolve_session(db, token) if token else None
    if s is None:
        raise HTTPException(401, "Not signed in")
    s.last_seen_at = utcnow()
    return s


def build_ctx(db: Session, s: AuthSession, ip: str | None) -> Ctx:
    if s.user_id:
        u = db.get(User, s.user_id)
        emp_id = None
        if u.employee_code:
            emp_id = db.scalar(select(Employee.id).where(Employee.org_id == u.org_id,
                                                         Employee.employee_code == u.employee_code))
        team = reporting_line(db, u.org_id, u.employee_code) if u.role == "manager" else frozenset()
        return Ctx(org_id=u.org_id, user_id=u.id, user=u.email, role=u.role, employee_id=emp_id,
                   employee_code=u.employee_code, session_id=s.id, ip=ip, team=team)
    a = db.get(EmployeeAccount, s.employee_account_id)
    e = db.get(Employee, a.employee_id)
    return Ctx(org_id=a.org_id, user_id=None, user=f"employee:{e.employee_code}", role="employee",
               kind="employee", employee_id=e.id, employee_code=e.employee_code, session_id=s.id, ip=ip)


def get_any_ctx(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: str | None = Header(default=None),
) -> Ctx:
    """Signed in (staff or employee), MFA not yet required. Used by /auth/me and /auth/mfa/*."""
    return build_ctx(db, _session(db, session_cookie, authorization), client_ip(request))


def get_ctx(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: str | None = Header(default=None),
) -> Ctx:
    """Signed-in staff member who has completed MFA if their role requires it."""
    s = _session(db, session_cookie, authorization)
    if not s.user_id:
        raise HTTPException(403, "Staff access only")
    u = db.get(User, s.user_id)
    if mfa_required(u) and not s.mfa_verified:
        raise HTTPException(401, "Multi-factor authentication required")
    return build_ctx(db, s, client_ip(request))


def get_employee_ctx(
    request: Request,
    db: Session = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: str | None = Header(default=None),
) -> Ctx:
    s = _session(db, session_cookie, authorization)
    if not s.employee_account_id:
        raise HTTPException(403, "Employee self-service only")
    return build_ctx(db, s, client_ip(request))


def require(*roles: str) -> Callable[..., Ctx]:
    """Dependency: staff with one of `roles` (admin always passes)."""

    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if not ctx.has(*roles):
            raise HTTPException(403, f"Requires role: {' or '.join(('admin', *roles))}")
        return ctx

    return dep


ADMIN = require()
HR = require("hr")
LEGAL = require("legal")
FINANCE = require("finance")
PLAN_VIEWERS = require("hr", "legal", "finance", "approver", "viewer")
CASE_VIEWERS = require("hr", "legal", "finance", "approver", "viewer", "manager")
