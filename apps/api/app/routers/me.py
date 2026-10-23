"""Employee self-service: an employee sees only their own case, never scores, other people, or plan details."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, grievances, storage
from app.crypto import decrypt_str
from app.db import get_db
from app.deps import Ctx, get_employee_ctx
from app.exits.states import LABELS
from app.models import (
    Acknowledgement,
    Appeal,
    ClearanceItem,
    Document,
    ExitCase,
    FnfLine,
    FnfStatement,
    Grievance,
    NoticeMessage,
    Org,
)
from app.schemas import AppealIn, SelfGrievanceIn

router = APIRouter(prefix="/me", tags=["self-service"])


def _my_case(db: Session, ctx: Ctx) -> ExitCase:
    c = db.scalar(select(ExitCase).where(ExitCase.org_id == ctx.org_id, ExitCase.employee_id == ctx.employee_id,
                                         ExitCase.state != "withdrawn").order_by(ExitCase.id.desc()).limit(1))
    if c is None:
        raise HTTPException(404, "No exit case")
    return c


@router.get("/case")
def my_case(ctx: Ctx = Depends(get_employee_ctx), db: Session = Depends(get_db)):
    c = _my_case(db, ctx)
    org = db.get(Org, ctx.org_id)
    msgs = db.scalars(select(NoticeMessage).where(NoticeMessage.exit_case_id == c.id, NoticeMessage.is_test.is_(False),
                                                  NoticeMessage.status.in_(("sent", "delivered")))
                      .order_by(NoticeMessage.sent_at)).all()
    acks = {a.message_id: a.acknowledged_at for a in db.scalars(select(Acknowledgement).where(
        Acknowledgement.message_id.in_([m.id for m in msgs] or [0])))}
    fnf = db.scalar(select(FnfStatement).where(FnfStatement.exit_case_id == c.id,
                                               FnfStatement.status.in_(("approved", "paid")))
                    .order_by(FnfStatement.version.desc()))
    gs = []
    for g in db.scalars(select(Grievance).where(Grievance.exit_case_id == c.id).order_by(Grievance.id)):
        a = db.scalar(select(Appeal).where(Appeal.grievance_id == g.id))
        gs.append({"id": g.id, "ref": grievances.ref(g), "category": g.category, "status": g.status,
                   "logged_at": g.logged_at, "outcome": g.outcome, "outcome_reasons": g.outcome_reasons,
                   "can_appeal": g.status == "decided" and a is None,
                   "appeal": {"status": a.status, "outcome": a.outcome, "reasons": a.reasons} if a else None})
    audit.record(db, ctx, "exit_case", c.id, "self_service_view")
    db.commit()
    return {
        "company": (org.settings or {}).get("legal_name", org.name),
        "hr_contact": (org.settings or {}).get("hr_contact_email"),
        "state": c.state, "state_label": LABELS.get(c.state, c.state),
        "dates": {"notice_date": c.notice_date, "notice_days": c.notice_days, "pay_in_lieu": c.pay_in_lieu,
                  "last_working_day": c.actual_last_day or c.last_working_day},
        "notices": [{"id": m.id, "subject": m.subject, "sent_at": m.sent_at, "body": decrypt_str(m.body_enc)
                     .replace("[[ACK_LINK]]", "(use the Confirm receipt button)"), "acknowledged_at": acks.get(m.id)}
                    for m in msgs],
        "documents": [{"id": d.id, "title": d.title, "version": d.version, "issued_at": d.issued_at,
                       "password_protected": d.password_protected}
                      for d in db.scalars(select(Document).where(Document.exit_case_id == c.id,
                                                                 Document.employee_id == ctx.employee_id)
                                          .order_by(Document.id))],
        "fnf": {"version": fnf.version, "status": fnf.status, "net_paise": fnf.net_paise,
                "earnings_paise": fnf.earnings_paise, "deductions_paise": fnf.deductions_paise,
                "payment_due_on": fnf.payment_due_on, "paid_at": fnf.paid_at,
                "lines": [{"label": ln.label, "kind": ln.kind, "amount_paise": ln.amount_paise, "basis": ln.formula}
                          for ln in db.scalars(select(FnfLine).where(FnfLine.statement_id == fnf.id)
                                               .order_by(FnfLine.position))]} if fnf else None,
        "clearance": [{"label": i.label, "category": i.category, "status": i.status}
                      for i in db.scalars(select(ClearanceItem).where(ClearanceItem.exit_case_id == c.id)
                                          .order_by(ClearanceItem.id))],
        "grievances": gs,
    }


@router.post("/acknowledge/{message_id}")
def acknowledge(message_id: int, ctx: Ctx = Depends(get_employee_ctx), db: Session = Depends(get_db)):
    c = _my_case(db, ctx)
    m = db.scalar(select(NoticeMessage).where(NoticeMessage.id == message_id, NoticeMessage.exit_case_id == c.id,
                                              NoticeMessage.is_test.is_(False)))
    if m is None:
        raise HTTPException(404, "Notice not found")
    done = db.scalar(select(Acknowledgement).where(Acknowledgement.message_id == m.id))
    if done is None:
        done = Acknowledgement(org_id=ctx.org_id, message_id=m.id, employee_id=ctx.employee_id, ip=ctx.ip)
        db.add(done)
        db.flush()
        audit.record(db, ctx, "notice_message", m.id, "acknowledged", None, {"exit_case_id": c.id})
        db.commit()
    return {"acknowledged_at": done.acknowledged_at}


@router.get("/documents/{doc_id}/download")
def download(doc_id: int, ctx: Ctx = Depends(get_employee_ctx), db: Session = Depends(get_db)):
    c = _my_case(db, ctx)
    d = db.scalar(select(Document).where(Document.id == doc_id, Document.exit_case_id == c.id,
                                         Document.employee_id == ctx.employee_id))
    if d is None:
        raise HTTPException(404, "Document not found")
    audit.record(db, ctx, "document", d.id, "employee_download", None, {"exit_case_id": c.id})
    db.commit()
    return Response(storage.load(d.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d.kind}-v{d.version}.pdf"'})


@router.post("/grievances", status_code=201)
def log_grievance(body: SelfGrievanceIn, ctx: Ctx = Depends(get_employee_ctx), db: Session = Depends(get_db)):
    c = _my_case(db, ctx)
    g = grievances.log(db, ctx, c, body.category, body.description)
    db.commit()
    return {"id": g.id, "ref": grievances.ref(g), "status": g.status}


@router.post("/grievances/{grievance_id}/appeal", status_code=201)
def appeal(grievance_id: int, body: AppealIn, ctx: Ctx = Depends(get_employee_ctx), db: Session = Depends(get_db)):
    c = _my_case(db, ctx)
    g = db.scalar(select(Grievance).where(Grievance.id == grievance_id, Grievance.exit_case_id == c.id))
    if g is None:
        raise HTTPException(404, "Grievance not found")
    grievances.appeal(db, ctx, g, body.grounds)
    db.commit()
    return {"status": "appealed"}
