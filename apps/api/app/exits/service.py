"""Exit case operations. State changes go through exits/states.py; approvals through workflow/approvals.py."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.crypto import content_hash
from app.deps import Ctx
from app.exits import notice_period, states
from app.exits.tasks import cancel_open, ensure_tasks
from app.models import (
    ClearanceItem,
    Employee,
    Evidence,
    ExitCase,
    ExitTask,
    NoticeDraft,
    Plan,
    PlanOverride,
    PlanResult,
    User,
    utcnow,
)
from app.notices import cancel_unsent_for_case, reason_hash
from app.queue import enqueue
from app.reasons import CODES, protected_terms_in
from app.workflow import approvals


def visible_cases(ctx: Ctx):
    q = select(ExitCase).where(ExitCase.org_id == ctx.org_id)
    if ctx.role == "manager":
        q = q.join(Employee, Employee.id == ExitCase.employee_id).where(
            Employee.employee_code.in_(ctx.team or {"__none__"}))
    return q


def get_case(db: Session, ctx: Ctx, case_id: int) -> ExitCase:
    c = db.scalar(visible_cases(ctx).where(ExitCase.id == case_id))
    if c is None:
        raise HTTPException(404, "Exit case not found")
    return c


def create_from_plan(db: Session, ctx: Ctx, plan: Plan) -> list[ExitCase]:
    if plan.status != "approved":
        raise HTTPException(409, "Exit cases can only be created from an approved plan")
    existing = set(db.scalars(select(ExitCase.employee_id).where(ExitCase.plan_id == plan.id)))
    overrides = {o.employee_id for o in db.scalars(select(PlanOverride).where(
        PlanOverride.plan_id == plan.id, PlanOverride.revoked.is_(False), PlanOverride.action == "include"))}
    created = []
    for r in db.scalars(select(PlanResult).where(PlanResult.plan_id == plan.id, PlanResult.final_selected.is_(True))):
        if r.employee_id in existing:
            continue
        basis = "manual" if plan.selection_method == "manual_list" else (
            "override" if r.employee_id in overrides else "algorithm")
        e = db.get(Employee, r.employee_id)
        c = ExitCase(org_id=ctx.org_id, plan_id=plan.id, employee_id=r.employee_id, owner=ctx.user,
                     selection_basis=basis, created_by=ctx.user,
                     reason_code="RED-ROLE" if plan.selection_method == "role_redundancy"
                     and e.role in (plan.eliminated_roles or []) else None)
        db.add(c)
        db.flush()
        ensure_tasks(db, c, "identified")
        audit.record(db, ctx, "exit_case", c.id, "create", None,
                     {"plan_id": plan.id, "employee_id": r.employee_id, "selection_basis": basis})
        created.append(c)
    return created


def set_reason(db: Session, ctx: Ctx, case: ExitCase, code: str, detail: str | None, evidence_ids: list[int]) -> None:
    states.require_active(case)
    if states.reached(case, "notice_sent"):
        raise HTTPException(409, "The reason can't change after the notice was sent")
    if code not in CODES:
        raise HTTPException(422, f"Unknown reason code {code}")
    terms = protected_terms_in(detail)
    if terms:
        raise HTTPException(422, f"Reason text can't cite protected characteristics or leave: {', '.join(terms)}")
    if code == "OTHER" and not (detail and len(detail.strip()) >= 20):
        raise HTTPException(422, "An 'Other' reason needs a written justification of at least 20 characters")
    ev = list(db.scalars(select(Evidence.id).where(Evidence.org_id == ctx.org_id, Evidence.entity_type == "exit_case",
                                                   Evidence.entity_id == case.id)))
    unknown = [i for i in evidence_ids if i not in ev]
    if unknown:
        raise HTTPException(422, f"Evidence not attached to this case: {unknown}")
    before = {"reason_code": case.reason_code, "reason_detail": case.reason_detail, "version": case.reason_version}
    case.reason_code, case.reason_detail, case.reason_evidence_ids = code, detail, evidence_ids
    case.reason_version += 1
    audit.record(db, ctx, "exit_case", case.id, "set_reason", before,
                 {"reason_code": code, "version": case.reason_version, "evidence_ids": evidence_ids})
    if code == "OTHER":
        approvals.start(db, ctx, "reason_other", case.id, reason_hash(case))


def set_dates(db: Session, ctx: Ctx, case: ExitCase, notice_date: date, pay_in_lieu: bool) -> dict:
    states.require_active(case)
    if states.reached(case, "notice_sent"):
        raise HTTPException(409, "Dates can't change after the notice was sent")
    if db.scalar(select(NoticeDraft.id).where(NoticeDraft.exit_case_id == case.id, NoticeDraft.status == "in_batch")):
        raise HTTPException(409, "A notice for this case is in a batch; remove it from the batch before changing dates")
    e = db.get(Employee, case.employee_id)
    plan = db.get(Plan, case.plan_id)
    try:
        r = notice_period.compute(e, rulebook(db, ctx.org_id, plan.ruleset_id), notice_date, pay_in_lieu)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    before = {"notice_date": case.notice_date, "pay_in_lieu": case.pay_in_lieu, "lwd": case.last_working_day}
    case.notice_date, case.pay_in_lieu = notice_date, pay_in_lieu
    case.notice_days, case.last_working_day, case.lwd_trace = r.days, r.last_working_day, {"steps": r.trace}
    for d in db.scalars(select(NoticeDraft).where(NoticeDraft.exit_case_id == case.id, NoticeDraft.status == "draft")):
        d.status = "superseded"  # drafts quoted the old dates
    audit.record(db, ctx, "exit_case", case.id, "set_dates", before,
                 {"notice_date": notice_date, "pay_in_lieu": pay_in_lieu, "notice_days": r.days,
                  "last_working_day": r.last_working_day})
    return {"notice_days": r.days, "last_working_day": r.last_working_day, "trace": r.trace}


def confirm_last_day(db: Session, ctx: Ctx, case: ExitCase, actual_last_day: date | None) -> None:
    states.require_active(case)
    if not states.reached(case, "notice_sent"):
        raise HTTPException(409, "The notice hasn't been sent yet")
    if actual_last_day and case.last_working_day and actual_last_day > case.last_working_day:
        raise HTTPException(422, "The actual last day can't be after the computed last working day")
    case.actual_last_day = actual_last_day or case.last_working_day
    short = notice_period.shortfall_days(case.last_working_day, case.actual_last_day, case.pay_in_lieu)
    audit.record(db, ctx, "exit_case", case.id, "confirm_last_day", None,
                 {"actual_last_day": case.actual_last_day, "shortfall_days": short})
    states.advance(db, ctx, case, "last_day_set")


def hold(db: Session, ctx: Ctx, case: ExitCase, reason: str) -> None:
    states.hold(db, ctx, case, reason)


def release_hold(db: Session, ctx: Ctx, case: ExitCase, note: str) -> None:
    states.release(db, ctx, case, note)


def withdraw(db: Session, ctx: Ctx, case: ExitCase, reason: str) -> None:
    if case.state in ("effective", "closed", "withdrawn"):
        raise HTTPException(409, f"A case that is {case.state} can't be withdrawn")
    cancelled = cancel_unsent_for_case(db, case)
    cancel_open(db, case)
    e = db.get(Employee, case.employee_id)
    if e.status == "on_notice":
        e.status = "active"
    before = case.state
    case.state, case.withdrawn_reason, case.held_from_state = "withdrawn", reason, None
    audit.record(db, ctx, "exit_case", case.id, "withdraw", {"state": before},
                 {"state": "withdrawn", "cancelled_messages": cancelled}, reason)


def clearance_complete(db: Session, case: ExitCase) -> bool:
    items = db.scalars(select(ClearanceItem).where(ClearanceItem.exit_case_id == case.id)).all()
    return bool(items) and all(i.status in ("verified", "returned", "done", "waived") for i in items)


def effective_hash(case: ExitCase) -> str:
    return content_hash({"case": case.id, "lwd": case.actual_last_day or case.last_working_day,
                         "state": case.state, "reason": case.reason_code})


def _manager_users(db: Session, case: ExitCase) -> list[str]:
    e = db.get(Employee, case.employee_id)
    if not e.manager_code:
        return []
    return list(db.scalars(select(User.email).where(User.org_id == case.org_id, User.employee_code == e.manager_code)))


def request_effective(db: Session, ctx: Ctx, case: ExitCase) -> None:
    states.require_active(case)
    if case.state != "documents_issued":
        raise HTTPException(409, "Documents must be issued before the exit can be marked effective")
    approvals.start(db, ctx, "exit_effective", case.id, effective_hash(case))


def decide_effective(db: Session, ctx: Ctx, case: ExitCase, approve: bool, comment: str | None) -> bool:
    states.require_active(case)
    forbidden = {case.owner: "You manage this case, so you can't approve its exit"}
    for m in _manager_users(db, case):
        forbidden[m] = "You manage this employee, so you can't approve their exit"
    _, finished = approvals.decide(db, ctx, "exit_effective", case.id, approve, comment, effective_hash(case), forbidden)
    if finished:
        states.advance(db, ctx, case, "effective")
        case.effective_at = utcnow()
        db.get(Employee, case.employee_id).status = "exited"
    return finished


def close(db: Session, ctx: Ctx, case: ExitCase) -> None:
    if case.state != "effective":
        raise HTTPException(409, "Only effective cases can be closed")
    open_tasks = [t.title for t in db.scalars(select(ExitTask).where(
        ExitTask.exit_case_id == case.id, ExitTask.status == "open", ExitTask.auto_key != "close_case"))]
    if open_tasks:
        raise HTTPException(409, f"Open tasks remain: {'; '.join(open_tasks[:5])}")
    for t in db.scalars(select(ExitTask).where(ExitTask.exit_case_id == case.id, ExitTask.auto_key == "close_case")):
        t.status, t.completed_by, t.completed_at = "done", ctx.user, utcnow()
    states.advance(db, ctx, case, "closed")
    case.closed_at = utcnow()


def hris_hash(case: ExitCase) -> str:
    return content_hash({"case": case.id, "effective_at": case.effective_at, "lwd": case.actual_last_day
                         or case.last_working_day})


def request_hris_push(db: Session, ctx: Ctx, case: ExitCase) -> None:
    if case.state not in ("effective", "closed"):
        raise HTTPException(409, "Only effective exits can be written to the HRIS")
    approvals.start(db, ctx, "hris_push", case.id, hris_hash(case))


def decide_hris_push(db: Session, ctx: Ctx, case: ExitCase, approve: bool, comment: str | None) -> bool:
    _, finished = approvals.decide(db, ctx, "hris_push", case.id, approve, comment, hris_hash(case))
    if finished:
        enqueue(db, ctx.org_id, "hris_push", {"exit_case_id": case.id, "approved_by": ctx.user})
    return finished
