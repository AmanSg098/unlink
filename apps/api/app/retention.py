"""Retention and data-subject tooling.

Defaults (org setting `retention` can override): closed-case personal data is pseudonymised 3 years after exit;
draft plans never submitted are deleted after 1 year; plans and the audit log are kept (7 years by policy; the
audit log is append-only, so expiry is handled by archiving outside the application). Legal hold blocks both.
"""

from datetime import timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.deps import Ctx
from app.models import (
    Checkin,
    Employee,
    EmployeeAccount,
    ExitCase,
    Feedback,
    Goal,
    Org,
    PayrollInput,
    Pip,
    Plan,
    QueueJob,
    Review,
    utcnow,
)
from app.worker import handler

DEFAULTS = {"closed_case_personal_years": 3, "draft_plan_years": 1, "plans_years": 7, "audit_years": 7}


def policy(org: Org) -> dict:
    return {**DEFAULTS, **((org.settings or {}).get("retention") or {})}


def pseudonymise(db: Session, org_id: int, actor: str, e: Employee, reason: str) -> None:
    if e.legal_hold:
        raise HTTPException(423, "This person is under legal hold")
    if e.pseudonymised_at:
        return
    e.full_name = f"Former employee {e.employee_code}"
    e.email = e.personal_email = None
    e.salary_breakup, e.custom_metrics = {}, {}
    e.gender = e.age_band = "withheld"
    e.pseudonymised_at = utcnow()
    db.execute(delete(EmployeeAccount).where(EmployeeAccount.employee_id == e.id))
    audit.record_raw(db, org_id, actor, "employee", e.id, "pseudonymise", None, {"employee_code": e.employee_code},
                     reason)


def export_person(db: Session, ctx: Ctx, e: Employee) -> dict:
    """Everything held about one person, for a data subject access request."""
    def rows(model, **flt):
        q = select(model).where(model.org_id == ctx.org_id, *[getattr(model, k) == v for k, v in flt.items()])
        return [{c.name: getattr(r, c.name) for c in model.__table__.columns
                 if not c.name.endswith("_enc") and c.name != "storage_key"} for r in db.scalars(q)]

    data = {
        "employee": {c.name: getattr(e, c.name) for c in Employee.__table__.columns},
        "reviews": rows(Review, employee_id=e.id), "goals": rows(Goal, employee_id=e.id),
        "checkins": rows(Checkin, employee_id=e.id), "feedback": rows(Feedback, employee_id=e.id),
        "pips": rows(Pip, employee_id=e.id), "payroll_inputs": rows(PayrollInput, employee_id=e.id),
        "exit_cases": rows(ExitCase, employee_id=e.id),
    }
    audit.record(db, ctx, "employee", e.id, "data_export", None, {"sections": list(data)})
    return data


@handler("retention_sweep")
def retention_sweep(db: Session, job: QueueJob) -> None:
    org = db.get(Org, job.org_id)
    p = policy(org)
    now = utcnow()
    cutoff = now - timedelta(days=365 * p["closed_case_personal_years"])
    for c in db.scalars(select(ExitCase).where(ExitCase.org_id == org.id, ExitCase.state == "closed")):
        closed = c.closed_at if c.closed_at is None or c.closed_at.tzinfo else c.closed_at.replace(tzinfo=timezone.utc)
        e = db.get(Employee, c.employee_id)
        if closed and closed <= cutoff and not e.legal_hold and not e.pseudonymised_at:
            pseudonymise(db, org.id, "system:retention", e, f"Retention: closed {p['closed_case_personal_years']}+ years")
    plan_cutoff = now - timedelta(days=365 * p["draft_plan_years"])
    for pl in db.scalars(select(Plan).where(Plan.org_id == org.id, Plan.status == "draft", Plan.submitted_at.is_(None))):
        created = pl.created_at if pl.created_at.tzinfo else pl.created_at.replace(tzinfo=timezone.utc)
        if created <= plan_cutoff and not db.scalar(select(ExitCase.id).where(ExitCase.plan_id == pl.id)):
            audit.record_raw(db, org.id, "system:retention", "plan", pl.id, "delete", {"name": pl.name}, None,
                             f"Retention: unsubmitted draft older than {p['draft_plan_years']} year(s)")
            db.delete(pl)
