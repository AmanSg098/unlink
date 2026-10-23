"""FNF workflow: compute a versioned statement, submit, approve (Finance, plus Legal when compensation or
gratuity is present), export, and record payment. Approval locks a statement; changes create a new version."""

import csv
import io

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.crypto import content_hash
from app.deps import Ctx
from app.exits import notice_period, states
from app.fnf.calculator import compute, context_for, what_if
from app.models import Employee, ExitCase, FnfLine, FnfStatement, PayrollInput, Plan, utcnow
from app.workflow import approvals


def payroll_input(db: Session, employee_id: int) -> PayrollInput | None:
    return db.scalar(select(PayrollInput).where(PayrollInput.employee_id == employee_id)
                     .order_by(PayrollInput.period.desc()).limit(1))


def _context(db: Session, case: ExitCase, pay_in_lieu: bool | None = None):
    e = db.get(Employee, case.employee_id)
    plan = db.get(Plan, case.plan_id)
    book = rulebook(db, case.org_id, plan.ruleset_id)
    pi = payroll_input(db, e.id)
    if pi is None:
        raise HTTPException(422, "No payroll inputs for this employee; import or enter them first")
    lwd = case.actual_last_day or case.last_working_day
    if lwd is None:
        raise HTTPException(409, "The last working day isn't set")
    pil = case.pay_in_lieu if pay_in_lieu is None else pay_in_lieu
    short = notice_period.shortfall_days(case.last_working_day, case.actual_last_day, pil)
    return context_for(e, book, pi.data, lwd, pil, case.notice_days or 0, short, case.reason_code), book, pi


def statement_hash(st: FnfStatement, lines: list[FnfLine]) -> str:
    return content_hash({"case": st.exit_case_id, "version": st.version, "net": st.net_paise, "inputs": st.inputs,
                         "lines": [(ln.component, ln.kind, ln.amount_paise, ln.rule_key) for ln in lines]})


def lines_of(db: Session, st: FnfStatement) -> list[FnfLine]:
    return list(db.scalars(select(FnfLine).where(FnfLine.statement_id == st.id).order_by(FnfLine.position)))


def compute_draft(db: Session, ctx: Ctx, case: ExitCase) -> FnfStatement:
    states.require_active(case)
    if not states.reached(case, "last_day_set"):
        raise HTTPException(409, "FNF can be computed once the last working day is set")
    if db.scalar(select(FnfStatement.id).where(FnfStatement.exit_case_id == case.id, FnfStatement.status == "paid")):
        raise HTTPException(409, "FNF has already been paid")
    fctx, book, pi = _context(db, case)
    res = compute(fctx)
    for old in db.scalars(select(FnfStatement).where(FnfStatement.exit_case_id == case.id,
                                                     FnfStatement.status.in_(("draft", "submitted", "rejected")))):
        old.status = "superseded"
    version = (db.scalar(select(func.max(FnfStatement.version)).where(FnfStatement.exit_case_id == case.id)) or 0) + 1
    st = FnfStatement(org_id=ctx.org_id, exit_case_id=case.id, version=version, status="draft",
                      pay_in_lieu=fctx.pay_in_lieu, earnings_paise=res.earnings, deductions_paise=res.deductions,
                      net_paise=res.net, inputs={"period": pi.period, "payroll": pi.data, "last_working_day":
                                                 fctx.last_working_day.isoformat(), "notice_days": fctx.notice_days,
                                                 "shortfall_days": fctx.shortfall_days, "reason_code": fctx.reason_code,
                                                 "rounding_adjustment": res.rounding_adjustment},
                      ruleset_id=book.ruleset.id if book.ruleset else None, needs_legal=res.needs_legal,
                      content_hash="", computed_by=ctx.user, payment_due_on=res.payment_due_on)
    db.add(st)
    db.flush()
    lines = []
    for i, ln in enumerate(res.lines):
        fl = FnfLine(org_id=ctx.org_id, statement_id=st.id, position=i, kind=ln.kind, component=ln.component,
                     label=ln.label, amount_paise=ln.amount_paise, rule_key=ln.rule_key, formula=ln.formula,
                     inputs=ln.inputs)
        db.add(fl)
        lines.append(fl)
    db.flush()
    st.content_hash = statement_hash(st, lines)
    audit.record(db, ctx, "fnf", st.id, "compute", None,
                 {"exit_case_id": case.id, "version": version, "net_paise": st.net_paise, "lines": len(lines),
                  "needs_legal": st.needs_legal})
    if case.state != "on_hold":
        states.advance(db, ctx, case, "fnf_draft")
    return st


def get_statement(db: Session, ctx: Ctx, st_id: int) -> FnfStatement:
    st = db.scalar(select(FnfStatement).where(FnfStatement.id == st_id, FnfStatement.org_id == ctx.org_id))
    if st is None:
        raise HTTPException(404, "FNF statement not found")
    return st


def submit(db: Session, ctx: Ctx, st: FnfStatement) -> None:
    case = db.get(ExitCase, st.exit_case_id)
    states.require_active(case)
    if st.status != "draft":
        raise HTTPException(409, f"Statement is {st.status}")
    if st.content_hash != statement_hash(st, lines_of(db, st)):
        raise HTTPException(409, "Statement content doesn't match its hash")
    st.status = "submitted"
    approvals.start(db, ctx, "fnf", st.id, st.content_hash, conditions={"needs_legal": st.needs_legal})
    audit.record(db, ctx, "fnf", st.id, "submit", None, {"exit_case_id": case.id, "version": st.version})


def decide(db: Session, ctx: Ctx, st: FnfStatement, approve: bool, comment: str | None) -> bool:
    case = db.get(ExitCase, st.exit_case_id)
    states.require_active(case)
    if st.status != "submitted":
        raise HTTPException(409, f"Statement is {st.status}")
    forbidden = {st.computed_by: "You computed this statement, so you can't approve it"}
    _, finished = approvals.decide(db, ctx, "fnf", st.id, approve, comment, statement_hash(st, lines_of(db, st)),
                                   forbidden)
    if not approve:
        st.status = "draft"
        return False
    if finished:
        for old in db.scalars(select(FnfStatement).where(FnfStatement.exit_case_id == case.id,
                                                         FnfStatement.status == "approved", FnfStatement.id != st.id)):
            old.status = "superseded"
        st.status = "approved"
        states.advance(db, ctx, case, "fnf_approved")
    return finished


def mark_paid(db: Session, ctx: Ctx, st: FnfStatement, reference: str) -> None:
    if st.status != "approved":
        raise HTTPException(409, "Only an approved statement can be marked paid")
    st.status, st.paid_at, st.payment_reference = "paid", utcnow(), reference
    audit.record(db, ctx, "fnf", st.id, "mark_paid", {"status": "approved"},
                 {"status": "paid", "reference": reference, "exit_case_id": st.exit_case_id})


def compare(db: Session, case: ExitCase) -> dict:
    fctx, _, _ = _context(db, case)
    return what_if(fctx)


def export_csv(db: Session, statements: list[FnfStatement]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["employee_code", "exit_case_id", "statement_version", "status", "last_working_day", "component",
                "kind", "amount_paise", "rule", "net_paise", "payment_due_on"])
    for st in statements:
        case = db.get(ExitCase, st.exit_case_id)
        e = db.get(Employee, case.employee_id)
        for ln in lines_of(db, st):
            w.writerow([e.employee_code, case.id, st.version, st.status, st.inputs.get("last_working_day"),
                        ln.component, ln.kind, ln.amount_paise, ln.rule_key or "", st.net_paise, st.payment_due_on])
    return buf.getvalue()
