from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit, people, storage
from app.crypto import decrypt_str
from app.db import get_db
from app.deps import ADMIN, Ctx, get_ctx, require
from app.importer import import_payroll, import_people
from app.models import (
    Checkin,
    CheckinAction,
    Employee,
    EmployeeHistory,
    Evidence,
    ExitCase,
    Feedback,
    Goal,
    PayrollInput,
    Pip,
    PipMilestone,
    Review,
    ReviewCycle,
)
from app.retention import export_person, pseudonymise
from app.schemas import EmployeeIn, EmployeePatch, PayrollInputIn
from app.scoring.exclusions import build_context, hard_exclusion_reason
from app.serialize import to_dict

router = APIRouter(prefix="/employees", tags=["people"])
STAFF_VIEW = require("hr", "legal", "finance", "approver", "viewer", "manager")
PAYROLL = require("hr", "finance")


async def _text(file: UploadFile) -> str:
    try:
        return (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "File must be UTF-8 CSV") from exc


@router.get("")
def list_employees(department: str | None = None, location: str | None = None, q: str | None = None,
                   status: str | None = None, ctx: Ctx = Depends(STAFF_VIEW), db: Session = Depends(get_db)):
    stmt = people.visible_query(ctx)
    if department:
        stmt = stmt.where(Employee.department == department)
    if location:
        stmt = stmt.where(Employee.location == location)
    if status:
        stmt = stmt.where(Employee.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like), Employee.employee_code.ilike(like)))
    xc = build_context(db, ctx.org_id, date.today())
    return [people.to_out(e, ctx, hard_exclusion_reason(e, xc)) for e in db.scalars(stmt.order_by(Employee.employee_code))]


@router.get("/meta")
def meta(ctx: Ctx = Depends(STAFF_VIEW), db: Session = Depends(get_db)):
    emps = list(db.scalars(people.visible_query(ctx)))
    xc = build_context(db, ctx.org_id, date.today())
    return {
        "total": len(emps), "hard_excluded": sum(hard_exclusion_reason(e, xc) is not None for e in emps),
        "departments": sorted({e.department for e in emps}), "locations": sorted({e.location for e in emps}),
        "roles": sorted({e.role for e in emps}), "metrics": sorted({k for e in emps for k in (e.custom_metrics or {})}),
        "by_status": {s: sum(1 for e in emps if e.status == s) for s in ("active", "on_notice", "exited", "on_hold")},
    }


@router.get("/by-code/{code}")
def profile(code: str, ctx: Ctx = Depends(STAFF_VIEW), db: Session = Depends(get_db)):
    e = people.get_by_code(db, ctx, code)
    xc = build_context(db, ctx.org_id, date.today())
    reviews = db.execute(select(Review, ReviewCycle).join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
                         .where(Review.employee_id == e.id).order_by(ReviewCycle.period_end.desc())).all()
    checkins = []
    for c in db.scalars(select(Checkin).where(Checkin.employee_id == e.id).order_by(Checkin.scheduled_for.desc())):
        actions = db.scalars(select(CheckinAction).where(CheckinAction.checkin_id == c.id)).all()
        checkins.append(to_dict(c, private_note=decrypt_str(c.private_note_enc) if c.private_note_enc and
                                c.created_by == ctx.user else None, has_private_note=bool(c.private_note_enc),
                                actions=[to_dict(a) for a in actions]))
    pips = []
    for p in db.scalars(select(Pip).where(Pip.employee_id == e.id).order_by(Pip.start_date.desc())):
        ms = db.scalars(select(PipMilestone).where(PipMilestone.pip_id == p.id).order_by(PipMilestone.on_date)).all()
        pips.append(to_dict(p, milestones=[to_dict(m) for m in ms]))
    show_sensitive = ctx.has("hr", "legal")
    out = {
        "employee": people.to_out(e, ctx, hard_exclusion_reason(e, xc)),
        "reviews": [{"cycle": cy.name, "cycle_id": cy.id, "period_end": cy.period_end, **to_dict(r)} for r, cy in reviews],
        "goals": [to_dict(g) for g in db.scalars(select(Goal).where(Goal.employee_id == e.id).order_by(Goal.id.desc()))],
        "checkins": checkins,
        "feedback": [to_dict(f, author=f.author if ctx.has("hr", "legal") or f.author == ctx.user else "hidden")
                     for f in db.scalars(select(Feedback).where(Feedback.employee_id == e.id)
                                         .order_by(Feedback.given_on.desc()))],
        "pips": pips,
        "evidence": [to_dict(v) for v in db.scalars(select(Evidence).where(Evidence.employee_id == e.id)
                                                    .order_by(Evidence.id.desc()))],
        "exit_cases": [{"id": c.id, "plan_id": c.plan_id, "state": c.state, "reason_code": c.reason_code,
                        "last_working_day": c.last_working_day}
                       for c in db.scalars(select(ExitCase).where(ExitCase.employee_id == e.id))],
        "history": [to_dict(h) for h in db.scalars(select(EmployeeHistory).where(EmployeeHistory.employee_id == e.id)
                                                   .order_by(EmployeeHistory.id.desc()).limit(100))]
        if show_sensitive else [],
    }
    return out


@router.post("", status_code=201)
def create_employee(body: EmployeeIn, ctx: Ctx = Depends(require("hr")), db: Session = Depends(get_db)):
    if db.scalar(select(Employee).where(Employee.org_id == ctx.org_id, Employee.employee_code == body.employee_code)):
        raise HTTPException(409, "An employee with this code already exists")
    e = Employee(org_id=ctx.org_id, **body.model_dump())
    db.add(e)
    db.flush()
    audit.record(db, ctx, "employee", e.id, "create", None, {"employee_code": e.employee_code})
    db.commit()
    return people.to_out(e, ctx)


@router.patch("/{employee_id}")
def update_employee(employee_id: int, body: EmployeePatch, ctx: Ctx = Depends(require("hr")),
                    db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    people.apply_changes(db, ctx, e, body.model_dump(exclude_unset=True))
    db.commit()
    return people.to_out(e, ctx)


@router.post("/import")
async def import_csv(file: UploadFile, ctx: Ctx = Depends(require("hr")), db: Session = Depends(get_db)):
    result = import_people(db, ctx, await _text(file))
    db.commit()
    return result


@router.post("/payroll/import")
async def payroll_import(file: UploadFile, ctx: Ctx = Depends(PAYROLL), db: Session = Depends(get_db)):
    result = import_payroll(db, ctx, await _text(file))
    db.commit()
    return result


@router.get("/{employee_id}/payroll")
def get_payroll(employee_id: int, ctx: Ctx = Depends(PAYROLL), db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    return [to_dict(p) for p in db.scalars(select(PayrollInput).where(PayrollInput.employee_id == e.id)
                                           .order_by(PayrollInput.period.desc()))]


@router.put("/{employee_id}/payroll")
def put_payroll(employee_id: int, body: PayrollInputIn, ctx: Ctx = Depends(require("finance")),
                db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    data = {k: int(v) if k not in ("leave_encashable_days", "days_worked_final_month", "days_in_month",
                                   "bonus_months_worked") else v for k, v in body.data.items()}
    p = db.scalar(select(PayrollInput).where(PayrollInput.employee_id == e.id, PayrollInput.period == body.period))
    before = p.data if p else None
    if p is None:
        p = PayrollInput(org_id=ctx.org_id, employee_id=e.id, period=body.period, data=data, source="manual",
                         updated_by=ctx.user)
        db.add(p)
    else:
        p.data, p.source, p.updated_by = data, "manual", ctx.user
    db.flush()
    audit.record(db, ctx, "payroll", p.id, "update", before, data)
    db.commit()
    return to_dict(p)


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, ctx: Ctx = Depends(require("hr", "legal", "manager")),
                      db: Session = Depends(get_db)):
    ev = db.scalar(select(Evidence).where(Evidence.id == evidence_id, Evidence.org_id == ctx.org_id))
    if ev is None or (ev.employee_id and ctx.role == "manager" and
                      db.get(Employee, ev.employee_id).employee_code not in ctx.team):
        raise HTTPException(404, "Evidence not found")
    audit.record(db, ctx, "evidence", ev.id, "view", None, {"filename": ev.filename})
    db.commit()
    return Response(storage.load(ev.storage_key), media_type=ev.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{ev.filename}"'})


@router.get("/{employee_id}/export")
def data_export(employee_id: int, ctx: Ctx = Depends(require("legal")), db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    data = export_person(db, ctx, e)
    db.commit()
    return data


@router.post("/{employee_id}/pseudonymise")
def do_pseudonymise(employee_id: int, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    open_case = db.scalar(select(ExitCase.id).where(ExitCase.employee_id == e.id,
                                                    ExitCase.state.not_in(("closed", "withdrawn"))))
    if open_case:
        raise HTTPException(409, "This person has an open exit case")
    pseudonymise(db, ctx.org_id, ctx.user, e, "Data subject request")
    db.commit()
    return people.to_out(e, ctx)


@router.get("/{employee_id}")
def get_employee(employee_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    e = people.get_visible(db, ctx, employee_id)
    return people.to_out(e, ctx, hard_exclusion_reason(e, build_context(db, ctx.org_id, date.today())))
