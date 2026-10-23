from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, grievances
from app.crypto import decrypt_str
from app.db import get_db
from app.deps import Ctx, require
from app.exits.service import get_case
from app.models import Appeal, Employee, ExitCase, Grievance
from app.schemas import AppealDecisionIn, GrievanceDecisionIn, GrievanceIn
from app.serialize import to_dict

router = APIRouter(prefix="/grievances", tags=["grievances"])
HR_LEGAL = require("hr", "legal")


def _out(db: Session, g: Grievance, detail: bool = False) -> dict:
    e = db.get(Employee, g.employee_id)
    a = db.scalar(select(Appeal).where(Appeal.grievance_id == g.id))
    out = to_dict(g, ref=grievances.ref(g), employee={"employee_code": e.employee_code, "full_name": e.full_name},
                  appeal=to_dict(a) if a else None, case_state=db.get(ExitCase, g.exit_case_id).state
                  if g.exit_case_id else None)
    if detail:
        out["description"] = grievances.description(g)
        if a:
            out["appeal"]["grounds"] = decrypt_str(a.grounds_enc)
    return out


@router.get("")
def list_grievances(ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    return [_out(db, g) for g in db.scalars(select(Grievance).where(Grievance.org_id == ctx.org_id)
                                            .order_by(Grievance.status == "closed", Grievance.ack_due_on))]


@router.post("", status_code=201)
def log(body: GrievanceIn, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    case = get_case(db, ctx, body.exit_case_id)
    g = grievances.log(db, ctx, case, body.category, body.description)
    db.commit()
    return _out(db, g)


@router.get("/{grievance_id}")
def detail(grievance_id: int, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    g = grievances.get(db, ctx, grievance_id)
    audit.record(db, ctx, "grievance", g.id, "view", None, {"exit_case_id": g.exit_case_id})
    db.commit()
    return _out(db, g, detail=True)


@router.post("/{grievance_id}/acknowledge")
def acknowledge(grievance_id: int, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    g = grievances.get(db, ctx, grievance_id)
    grievances.acknowledge(db, ctx, g)
    db.commit()
    return _out(db, g)


@router.post("/{grievance_id}/decision")
def decide(grievance_id: int, body: GrievanceDecisionIn, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    g = grievances.get(db, ctx, grievance_id)
    grievances.decide(db, ctx, g, body.findings, body.outcome, body.reasons)
    db.commit()
    return _out(db, g)


@router.post("/{grievance_id}/appeal/decision")
def decide_appeal(grievance_id: int, body: AppealDecisionIn, ctx: Ctx = Depends(HR_LEGAL),
                  db: Session = Depends(get_db)):
    g = grievances.get(db, ctx, grievance_id)
    if g.status != "appealed":
        raise HTTPException(409, "There's no open appeal")
    grievances.decide_appeal(db, ctx, g, body.outcome, body.reasons)
    db.commit()
    return _out(db, g)
