from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import Ctx, require
from app.exits.service import visible_cases
from app.fnf import service as fnf
from app.models import Employee, ExitCase, FnfStatement
from app.schemas import DecisionIn, MarkPaidIn
from app.serialize import to_dict
from app.workflow import approvals

router = APIRouter(prefix="/fnf", tags=["fnf"])
VIEW = require("hr", "finance", "legal")


def _out(db: Session, ctx: Ctx, st: FnfStatement, lines: bool = False) -> dict:
    case = db.get(ExitCase, st.exit_case_id)
    e = db.get(Employee, case.employee_id)
    step = approvals.current_step(db, ctx.org_id, "fnf", st.id)
    out = to_dict(st, employee={"employee_code": e.employee_code, "full_name": e.full_name, "department": e.department},
                  case_state=case.state, current_step={"step": step.step, "roles": step.roles} if step else None)
    if lines:
        out["lines"] = [to_dict(ln) for ln in fnf.lines_of(db, st)]
        out["approvals"] = [to_dict(a) for a in approvals.history(db, ctx.org_id, "fnf", st.id)]
    return out


@router.get("")
def queue(status: str | None = None, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    case_ids = select(visible_cases(ctx).subquery().c.id)
    q = select(FnfStatement).where(FnfStatement.org_id == ctx.org_id, FnfStatement.exit_case_id.in_(case_ids))
    q = q.where(FnfStatement.status == status) if status else q.where(FnfStatement.status != "superseded")
    return [_out(db, ctx, st) for st in db.scalars(q.order_by(FnfStatement.id.desc()))]


@router.get("/{statement_id}")
def statement(statement_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    st = fnf.get_statement(db, ctx, statement_id)
    audit.record(db, ctx, "fnf", st.id, "view", None, {"exit_case_id": st.exit_case_id})  # sensitive view
    db.commit()
    return _out(db, ctx, st, lines=True)


@router.post("/{statement_id}/submit")
def submit(statement_id: int, ctx: Ctx = Depends(require("hr", "finance")), db: Session = Depends(get_db)):
    st = fnf.get_statement(db, ctx, statement_id)
    fnf.submit(db, ctx, st)
    db.commit()
    return _out(db, ctx, st, lines=True)


@router.post("/{statement_id}/decision")
def decide(statement_id: int, body: DecisionIn, ctx: Ctx = Depends(require("finance", "legal")),
           db: Session = Depends(get_db)):
    st = fnf.get_statement(db, ctx, statement_id)
    fnf.decide(db, ctx, st, body.approve, body.comment)
    db.commit()
    return _out(db, ctx, st, lines=True)


@router.post("/{statement_id}/mark-paid")
def mark_paid(statement_id: int, body: MarkPaidIn, ctx: Ctx = Depends(require("finance")),
              db: Session = Depends(get_db)):
    st = fnf.get_statement(db, ctx, statement_id)
    fnf.mark_paid(db, ctx, st, body.reference)
    db.commit()
    return _out(db, ctx, st, lines=True)


@router.get("/export/payroll.csv")
def export(ctx: Ctx = Depends(require("finance")), db: Session = Depends(get_db)):
    sts = db.scalars(select(FnfStatement).where(FnfStatement.org_id == ctx.org_id,
                                                FnfStatement.status.in_(("approved", "paid")))
                     .order_by(FnfStatement.id)).all()
    data = fnf.export_csv(db, sts)
    audit.record(db, ctx, "fnf", None, "export_payroll_csv", None, {"statements": len(sts)})
    db.commit()
    return Response(data, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="fnf-payroll.csv"'})
