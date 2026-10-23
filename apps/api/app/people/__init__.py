"""People: visibility by role, field masking, and change history."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.deps import Ctx
from app.models import Employee, EmployeeHistory

# Who may see which sensitive fields.
PAY_ROLES = ("hr", "finance", "legal")
SENSITIVE_ROLES = ("hr", "legal")  # leave, gender, age band, protection detail

BASIC = ["id", "employee_code", "full_name", "email", "department", "role", "location", "manager_code",
         "hire_date", "confirmation_date", "employment_type", "contract_end_date", "status",
         "performance_rating", "potential_rating", "critical_skill_score"]
PAY = ["annual_ctc_paise", "salary_breakup", "contract_notice_days"]
SENSITIVE = ["personal_email", "gender", "age_band", "leave_status", "protected_flag", "legal_hold", "custom_metrics"]

# Fields whose changes are written to employee_history.
TRACKED = ["full_name", "email", "personal_email", "department", "role", "location", "manager_code", "hire_date",
           "confirmation_date", "employment_type", "contract_end_date", "contract_notice_days", "annual_ctc_paise",
           "salary_breakup", "performance_rating", "potential_rating", "critical_skill_score", "gender", "age_band",
           "leave_status", "protected_flag", "legal_hold", "custom_metrics", "status"]


def visible_query(ctx: Ctx):
    q = select(Employee).where(Employee.org_id == ctx.org_id)
    if ctx.role == "manager":
        q = q.where(Employee.employee_code.in_(ctx.team or {"__none__"}))
    return q


def get_visible(db: Session, ctx: Ctx, employee_id: int) -> Employee:
    e = db.scalar(visible_query(ctx).where(Employee.id == employee_id))
    if e is None:
        raise HTTPException(404, "Employee not found")
    return e


def get_by_code(db: Session, ctx: Ctx, code: str) -> Employee:
    e = db.scalar(visible_query(ctx).where(Employee.employee_code == code))
    if e is None:
        raise HTTPException(404, "Employee not found")
    return e


def _jsonable(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def to_out(e: Employee, ctx: Ctx, exclusion_reason: str | None = None) -> dict:
    out = {k: _jsonable(getattr(e, k)) for k in BASIC}
    masked = []
    for k in PAY:
        if ctx.has(*PAY_ROLES):
            out[k] = getattr(e, k)
        else:
            out[k] = None
            masked.append(k)
    for k in SENSITIVE:
        if ctx.has(*SENSITIVE_ROLES):
            out[k] = getattr(e, k)
        else:
            out[k] = None
            masked.append(k)
    # Everyone may know someone is protected from selection; only HR/Legal see why.
    out["protected"] = exclusion_reason is not None
    out["exclusion_reason"] = exclusion_reason if ctx.has(*SENSITIVE_ROLES) else ("Protected" if exclusion_reason else None)
    out["masked"] = masked
    return out


def apply_changes(db: Session, ctx: Ctx, e: Employee, data: dict, action: str = "update") -> list[str]:
    """Set fields, write history rows and one audit entry. Returns the changed field names."""
    changed = [k for k in TRACKED if k in data and data[k] != getattr(e, k)]
    if not changed:
        return []
    before = {k: _jsonable(getattr(e, k)) for k in changed}
    for k in changed:
        db.add(EmployeeHistory(org_id=ctx.org_id, employee_id=e.id, field=k, old_value=before[k],
                               new_value=_jsonable(data[k]), changed_by=ctx.user))
        setattr(e, k, data[k])
    audit.record(db, ctx, "employee", e.id, action, before, {k: _jsonable(getattr(e, k)) for k in changed})
    return changed
