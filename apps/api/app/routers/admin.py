from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import end_all_sessions, hash_password
from app.config import MAIL_PROVIDER, live_mail_allowed
from app.db import get_db
from app.deps import ADMIN, Ctx, get_ctx
from app.importer import parse_people_csv
from app.integrations import PROVIDERS, enabled_integration, get_secrets, set_secrets
from app.models import Employee, Integration, IntegrationRun, Org, User
from app.people import apply_changes
from app.queue import enqueue
from app.schemas import IntegrationIn, OrgSettingsPatch, UserIn, UserPatch
from app.serialize import to_dict

router = APIRouter(tags=["admin"])


def _user(u: User) -> dict:
    return to_dict(u, exclude=("mfa_secret_enc",))


@router.get("/users")
def list_users(ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    return [_user(u) for u in db.scalars(select(User).where(User.org_id == ctx.org_id).order_by(User.email))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "A user with this email already exists")
    u = User(org_id=ctx.org_id, email=email, full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password), employee_code=body.employee_code)
    db.add(u)
    db.flush()
    audit.record(db, ctx, "user", u.id, "create", None, {"email": u.email, "role": u.role})
    db.commit()
    return _user(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.id == user_id, User.org_id == ctx.org_id))
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == ctx.user_id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(409, "You cannot deactivate or demote yourself")
    before = {"role": u.role, "active": u.active, "full_name": u.full_name, "employee_code": u.employee_code}
    data = body.model_dump(exclude_unset=True)
    after: dict = {}
    if (pw := data.pop("password", None)) is not None:
        u.password_hash = hash_password(pw)
        after["password"] = "changed"
    if data.pop("reset_mfa", False):
        u.mfa_secret_enc, u.mfa_enabled = None, False
        after["mfa"] = "reset"
        end_all_sessions(db, u.id)
    for k, v in data.items():
        setattr(u, k, v)
    if body.active is False or body.role is not None:
        end_all_sessions(db, u.id)  # role or access changes take effect immediately
    after |= {"role": u.role, "active": u.active, "full_name": u.full_name, "employee_code": u.employee_code}
    audit.record(db, ctx, "user", u.id, "update", before, after)
    db.commit()
    return _user(u)


@router.get("/org")
def get_org(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    org = db.get(Org, ctx.org_id)
    s = org.settings or {}
    return {"id": org.id, "name": org.name, "region": org.region, "timezone": org.timezone,
            "settings": {k: s.get(k) for k in ("legal_name", "address", "hr_contact_email", "test_addresses",
                                               "establishment_size", "escalation_days")},
            "reason_wording_approvals": s.get("reason_wording_approvals", {}),
            "mail": {"provider": MAIL_PROVIDER, "live": live_mail_allowed()}}


@router.patch("/org")
def update_org(body: OrgSettingsPatch, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    org = db.get(Org, ctx.org_id)
    data = body.model_dump(exclude_unset=True)
    before = {k: (org.settings or {}).get(k) for k in data}
    org.settings = {**(org.settings or {}), **{k: (list(map(str, v)) if isinstance(v, list) else v)
                                               for k, v in data.items()}}
    audit.record(db, ctx, "org", org.id, "update_settings", before, data)
    db.commit()
    return get_org(ctx, db)


# ------------------------------------------------------------------ integrations

def _integration(i: Integration) -> dict:
    return to_dict(i, secret_keys=sorted(get_secrets(i).keys()))


@router.get("/integrations")
def list_integrations(ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    rows = db.scalars(select(Integration).where(Integration.org_id == ctx.org_id)).all()
    runs = db.scalars(select(IntegrationRun).where(IntegrationRun.org_id == ctx.org_id)
                      .order_by(IntegrationRun.id.desc()).limit(20)).all()
    return {"providers": PROVIDERS, "integrations": [_integration(i) for i in rows],
            "runs": [to_dict(r) for r in runs], "mail": {"provider": MAIL_PROVIDER, "live": live_mail_allowed()}}


@router.put("/integrations")
def upsert_integration(body: IntegrationIn, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    spec = PROVIDERS.get(body.type, {}).get(body.provider)
    if spec is None:
        raise HTTPException(422, "Unknown integration type or provider")
    if spec.get("env"):
        raise HTTPException(422, "Email is configured with environment variables (MAIL_PROVIDER, SMTP_*)")
    if not spec.get("implemented") and body.enabled:
        raise HTTPException(422, f"{spec['label']} is planned but not implemented yet")
    i = db.scalar(select(Integration).where(Integration.org_id == ctx.org_id, Integration.type == body.type))
    if i is None:
        i = Integration(org_id=ctx.org_id, type=body.type, provider=body.provider, updated_by=ctx.user)
        db.add(i)
    before = {"provider": i.provider, "enabled": i.enabled, "config": i.config}
    i.provider, i.enabled, i.updated_by = body.provider, body.enabled, ctx.user
    i.config = {k: v for k, v in body.config.items() if k in spec.get("config", [])}
    set_secrets(i, {k: v for k, v in body.secrets.items() if k in spec.get("secrets", [])})
    db.flush()
    audit.record(db, ctx, "integration", i.id, "configure", before,
                 {"provider": i.provider, "enabled": i.enabled, "config": i.config,
                  "secrets_set": sorted(get_secrets(i).keys())})
    db.commit()
    return _integration(i)


@router.post("/integrations/hris/sync", status_code=202)
def hris_sync(ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    i = db.scalar(select(Integration).where(Integration.org_id == ctx.org_id, Integration.type == "hris",
                                            Integration.enabled.is_(True)))
    if i is None:
        raise HTTPException(409, "Enable an HRIS integration first")
    run = IntegrationRun(org_id=ctx.org_id, integration_id=i.id, kind="people_sync", status="running")
    db.add(run)
    db.flush()
    enqueue(db, ctx.org_id, "hris_sync", {"run_id": run.id})
    audit.record(db, ctx, "integration", i.id, "sync_requested", None, {"run_id": run.id})
    db.commit()
    return to_dict(run)


@router.post("/integrations/runs/{run_id}/apply")
def apply_sync(run_id: int, employee_codes: list[str], ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    """Apply reviewed HRIS changes for the chosen employees. Nothing is applied without this step."""
    run = db.scalar(select(IntegrationRun).where(IntegrationRun.id == run_id, IntegrationRun.org_id == ctx.org_id))
    if run is None or run.status != "needs_review":
        raise HTTPException(409, "This run has nothing waiting for review")
    integ = enabled_integration(db, ctx.org_id, "hris")
    rows, _ = parse_people_csv((Path(integ.config["inbox_path"]) / "people.csv").read_text())
    applied = []
    for code in employee_codes:
        e = db.scalar(select(Employee).where(Employee.org_id == ctx.org_id, Employee.employee_code == code))
        if e is not None and code in rows:
            if apply_changes(db, ctx, e, rows[code], action="hris_sync"):
                applied.append(code)
    run.summary = {**run.summary, "applied": sorted(set(run.summary.get("applied", [])) | set(applied))}
    db.commit()
    return {"applied": applied}
