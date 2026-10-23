import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, clearance, documents, reports, storage
from app.auth import token_hash
from app.compliance.rules import rulebook
from app.config import WEB_BASE_URL
from app.db import get_db
from app.deps import CASE_VIEWERS, Ctx, require
from app.exits import service as exits
from app.exits import states
from app.exits.states import LABELS, MAIN
from app.fnf import service as fnf
from app.mail import OutMail, send
from app.models import (
    Acknowledgement,
    Document,
    Employee,
    EmployeeAccount,
    Evidence,
    ExitCase,
    ExitTask,
    FnfStatement,
    Grievance,
    NoticeDraft,
    NoticeMessage,
    NoticeTemplate,
    Org,
    Plan,
    utcnow,
)
from app.notices import reason_hash
from app.performance import store_evidence
from app.reasons import CODES, evidence_status
from app.schemas import (
    CasesFromPlanIn,
    ClearanceIn,
    DatesIn,
    DecisionIn,
    DocumentIn,
    LastDayIn,
    ReasonIn,
    TaskPatch,
    TextIn,
)
from app.serialize import to_dict
from app.workflow import approvals

router = APIRouter(prefix="/exit-cases", tags=["exit cases"])
HR = require("hr")
HR_LEGAL = require("hr", "legal")
PAY_ROLES = ("hr", "finance", "legal")


def _summary(db: Session, ctx: Ctx, c: ExitCase) -> dict:
    e = db.get(Employee, c.employee_id)
    open_tasks = db.scalars(select(ExitTask).where(ExitTask.exit_case_id == c.id, ExitTask.status == "open")).all()
    overdue = sum(1 for t in open_tasks if t.due_date and t.due_date < date.today())
    return to_dict(c, employee={"id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
                                "department": e.department, "role": e.role, "manager_code": e.manager_code},
                   state_label=LABELS.get(c.state, c.state), open_tasks=len(open_tasks), overdue_tasks=overdue,
                   plan_name=db.get(Plan, c.plan_id).name)


@router.get("")
def list_cases(state: str | None = None, plan_id: int | None = None, ctx: Ctx = Depends(CASE_VIEWERS),
               db: Session = Depends(get_db)):
    q = exits.visible_cases(ctx)
    if state:
        q = q.where(ExitCase.state == state)
    if plan_id:
        q = q.where(ExitCase.plan_id == plan_id)
    return [_summary(db, ctx, c) for c in db.scalars(q.order_by(ExitCase.id.desc()))]


@router.post("", status_code=201)
def create_cases(body: CasesFromPlanIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = db.scalar(select(Plan).where(Plan.id == body.plan_id, Plan.org_id == ctx.org_id))
    if p is None:
        raise HTTPException(404, "Plan not found")
    created = exits.create_from_plan(db, ctx, p)
    db.commit()
    return [_summary(db, ctx, c) for c in created]


@router.get("/{case_id}")
def get_case(case_id: int, ctx: Ctx = Depends(CASE_VIEWERS), db: Session = Depends(get_db)):
    c = exits.get_case(db, ctx, case_id)
    e = db.get(Employee, c.employee_id)
    plan = db.get(Plan, c.plan_id)
    book = rulebook(db, ctx.org_id, plan.ruleset_id)
    approved_other = approvals.is_approved(db, ctx.org_id, "reason_other", c.id, reason_hash(c))
    msgs = db.scalars(select(NoticeMessage).where(NoticeMessage.exit_case_id == c.id, NoticeMessage.is_test.is_(False))
                      .order_by(NoticeMessage.id)).all()
    acks = {a.message_id: a.acknowledged_at for a in db.scalars(select(Acknowledgement).where(
        Acknowledgement.message_id.in_([m.id for m in msgs] or [0])))}
    drafts = db.scalars(select(NoticeDraft).where(NoticeDraft.exit_case_id == c.id, NoticeDraft.status != "superseded")
                        .order_by(NoticeDraft.id.desc())).all()
    sts = db.scalars(select(FnfStatement).where(FnfStatement.exit_case_id == c.id)
                     .order_by(FnfStatement.version.desc())).all() if ctx.has(*PAY_ROLES) else []
    account = db.scalar(select(EmployeeAccount).where(EmployeeAccount.employee_id == e.id))
    approval_steps = {k: [to_dict(a) for a in approvals.history(db, ctx.org_id, k, c.id)]
                      for k in ("exit_effective", "hris_push", "reason_other", "clearance_exception")}
    return {
        "case": _summary(db, ctx, c),
        "states": [{"key": s, "label": LABELS[s]} for s in MAIN],
        "reason": {"codes": [{"code": k, "name": v.name, "evidence": v.evidence, "evidence_type": v.evidence_type}
                             for k, v in CODES.items()],
                   "evidence": evidence_status(db, c, e, plan, book, approved_other),
                   "other_approved": approved_other},
        "evidence": [to_dict(v) for v in db.scalars(select(Evidence).where(
            Evidence.entity_type == "exit_case", Evidence.entity_id == c.id))],
        "tasks": [to_dict(t) for t in db.scalars(select(ExitTask).where(ExitTask.exit_case_id == c.id)
                                                 .order_by(ExitTask.status != "open", ExitTask.due_date))],
        "drafts": [to_dict(d, template=db.get(NoticeTemplate, d.template_id).title) for d in drafts],
        "messages": [to_dict(m, acknowledged_at=acks.get(m.id)) for m in msgs],
        "fnf": [to_dict(s) for s in sts],
        "documents": [to_dict(d) for d in db.scalars(select(Document).where(Document.exit_case_id == c.id)
                                                     .order_by(Document.id.desc()))],
        "clearance": [to_dict(i) for i in clearance.items(db, c)],
        "clearance_complete": clearance.complete(db, c),
        "grievances": [to_dict(g) for g in db.scalars(select(Grievance).where(Grievance.exit_case_id == c.id))],
        "approvals": approval_steps,
        "self_service": {"invited": account is not None, "active": bool(account and account.active)},
        "audit": [to_dict(a) for a in audit.for_entity(db, ctx, "exit_case", c.id,
                                                       related=("notice_message", "notice_draft", "fnf", "document",
                                                                "clearance", "grievance", "evidence"), limit=100)],
    }


def _case(db: Session, ctx: Ctx, case_id: int) -> ExitCase:
    return exits.get_case(db, ctx, case_id)


@router.post("/{case_id}/reason")
def set_reason(case_id: int, body: ReasonIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.set_reason(db, ctx, c, body.reason_code, body.reason_detail, body.evidence_ids)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/reason/decision")
def decide_other_reason(case_id: int, body: DecisionIn, ctx: Ctx = Depends(require("legal")),
                        db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    approvals.decide(db, ctx, "reason_other", c.id, body.approve, body.comment, reason_hash(c))
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/dates")
def set_dates(case_id: int, body: DatesIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    out = exits.set_dates(db, ctx, c, body.notice_date, body.pay_in_lieu)
    db.commit()
    return out


@router.post("/{case_id}/last-day")
def confirm_last_day(case_id: int, body: LastDayIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.confirm_last_day(db, ctx, c, body.actual_last_day)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/hold")
def hold(case_id: int, body: TextIn, ctx: Ctx = Depends(require("legal")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.hold(db, ctx, c, body.text)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/release-hold")
def release_hold(case_id: int, body: TextIn, ctx: Ctx = Depends(require("legal")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    open_g = db.scalar(select(Grievance.id).where(Grievance.exit_case_id == c.id,
                                                  Grievance.status.in_(("open", "under_review", "appealed"))))
    if open_g:
        raise HTTPException(409, "A grievance on this case is still open")
    exits.release_hold(db, ctx, c, body.text)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/withdraw")
def withdraw(case_id: int, body: TextIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.withdraw(db, ctx, c, body.text)
    db.commit()
    return _summary(db, ctx, c)


@router.patch("/{case_id}/tasks/{task_id}")
def update_task(case_id: int, task_id: int, body: TaskPatch, ctx: Ctx = Depends(CASE_VIEWERS),
                db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    t = db.scalar(select(ExitTask).where(ExitTask.id == task_id, ExitTask.exit_case_id == c.id))
    if t is None:
        raise HTTPException(404, "Task not found")
    if not (ctx.has(t.owner_role, "hr") or (t.owner_role == "manager" and ctx.role == "manager")):
        raise HTTPException(403, f"This task belongs to {t.owner_role}")
    before = t.status
    t.status = body.status
    t.completed_by, t.completed_at = (ctx.user, utcnow()) if body.status == "done" else (None, None)
    audit.record(db, ctx, "exit_task", t.id, "update", {"status": before}, {"status": body.status,
                                                                             "exit_case_id": c.id})
    db.commit()
    return to_dict(t)


@router.post("/{case_id}/evidence", status_code=201)
async def upload_case_evidence(case_id: int, evidence_type: str = Form(...), file: UploadFile = File(...),
                               ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    ev = store_evidence(db, ctx, employee_id=c.employee_id, entity_type="exit_case", entity_id=c.id,
                        evidence_type=evidence_type, filename=file.filename or "file", data=await file.read())
    db.commit()
    return to_dict(ev)


# ------------------------------------------------------------------ FNF
@router.post("/{case_id}/fnf", status_code=201)
def compute_fnf(case_id: int, ctx: Ctx = Depends(require("hr", "finance")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    st = fnf.compute_draft(db, ctx, c)
    db.commit()
    return to_dict(st, lines=[to_dict(ln) for ln in fnf.lines_of(db, st)])


@router.get("/{case_id}/fnf/what-if")
def fnf_what_if(case_id: int, ctx: Ctx = Depends(require("hr", "finance")), db: Session = Depends(get_db)):
    return fnf.compare(db, _case(db, ctx, case_id))


# ------------------------------------------------------------------ documents and clearance
@router.post("/{case_id}/documents", status_code=201)
def issue_document(case_id: int, body: DocumentIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    if c.state == "on_hold":
        raise HTTPException(423, "The case is on hold")
    if body.kind in ("relieving_letter", "experience_letter", "certificate_of_service"):
        if c.state not in ("fnf_approved", "documents_issued", "effective", "closed"):
            raise HTTPException(409, "Relieving documents are issued after the FNF is approved")
        if body.kind == "relieving_letter" and not (clearance.complete(db, c) or clearance.exception_approved(db, c)):
            raise HTTPException(409, "Clearance isn't complete. Finish it or get an approved clearance exception.")
    password = documents.new_password() if body.password_protect else None
    doc = documents.issue_for_case(db, ctx, c, body.kind, password)
    if body.kind == "relieving_letter":
        states.advance(db, ctx, c, "documents_issued")
    db.commit()
    return to_dict(doc, password=password)


@router.get("/{case_id}/documents/{doc_id}/download")
def download_document(case_id: int, doc_id: int, ctx: Ctx = Depends(require("hr", "legal", "finance")),
                      db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    d = db.scalar(select(Document).where(Document.id == doc_id, Document.exit_case_id == c.id))
    if d is None:
        raise HTTPException(404, "Document not found")
    audit.record(db, ctx, "document", d.id, "view", None, {"exit_case_id": c.id, "kind": d.kind})
    db.commit()
    return Response(storage.load(d.storage_key), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{d.kind}-v{d.version}.pdf"'})


@router.patch("/{case_id}/clearance/{item_id}")
def update_clearance(case_id: int, item_id: int, body: ClearanceIn, ctx: Ctx = Depends(CASE_VIEWERS),
                     db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    it = clearance.update(db, ctx, c, item_id, body.status, body.note)
    db.commit()
    return to_dict(it)


@router.post("/{case_id}/clearance/exception")
def request_clearance_exception(case_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    if clearance.complete(db, c):
        raise HTTPException(409, "Clearance is already complete")
    approvals.start(db, ctx, "clearance_exception", c.id, clearance.exception_hash(c, db))
    db.commit()
    return {"requested": True}


@router.post("/{case_id}/clearance/exception/decision")
def decide_clearance_exception(case_id: int, body: DecisionIn, ctx: Ctx = Depends(require("approver")),
                               db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    approvals.decide(db, ctx, "clearance_exception", c.id, body.approve, body.comment, clearance.exception_hash(c, db),
                     {c.owner: "You manage this case"})
    db.commit()
    return {"approved": clearance.exception_approved(db, c)}


# ------------------------------------------------------------------ effective, close, HRIS
@router.post("/{case_id}/mark-effective")
def request_effective(case_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.request_effective(db, ctx, c)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/mark-effective/decision")
def decide_effective(case_id: int, body: DecisionIn, ctx: Ctx = Depends(require("approver")),
                     db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.decide_effective(db, ctx, c, body.approve, body.comment)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/close")
def close_case(case_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.close(db, ctx, c)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/push-hris")
def request_hris(case_id: int, ctx: Ctx = Depends(require("finance")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.request_hris_push(db, ctx, c)
    db.commit()
    return _summary(db, ctx, c)


@router.post("/{case_id}/push-hris/decision")
def decide_hris(case_id: int, body: DecisionIn, ctx: Ctx = Depends(require("finance")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    exits.decide_hris_push(db, ctx, c, body.approve, body.comment)
    db.commit()
    return _summary(db, ctx, c)


# ------------------------------------------------------------------ self-service invite and exit file
@router.post("/{case_id}/invite")
def invite_employee(case_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    """Create (or refresh) the employee's self-service login and email them an invitation link.
    The message is fixed text with no case details; HR triggers each send explicitly."""
    c = _case(db, ctx, case_id)
    e = db.get(Employee, c.employee_id)
    email = e.personal_email or e.email
    if not email:
        raise HTTPException(422, "The employee has no email address on record")
    token = secrets.token_urlsafe(32)
    a = db.scalar(select(EmployeeAccount).where(EmployeeAccount.employee_id == e.id))
    if a is None:
        a = EmployeeAccount(org_id=ctx.org_id, employee_id=e.id, email=email.lower())
        db.add(a)
    a.invite_token_hash, a.invite_expires_at = token_hash(token), utcnow() + timedelta(days=7)
    db.flush()
    org = db.get(Org, ctx.org_id)
    company = (org.settings or {}).get("legal_name", org.name)
    send(db, OutMail(org_id=ctx.org_id, to=[a.email], subject=f"Your {company} self-service access",
                     text=f"Dear {e.full_name},\n\nYou can view your letters, dates and statements, confirm receipt, "
                          f"and raise a concern in your self-service page.\n\nSet your password here (valid 7 days): "
                          f"{WEB_BASE_URL}/me/activate?token={token}\n\nHuman Resources, {company}\n"))
    audit.record(db, ctx, "exit_case", c.id, "invite_self_service", None, {"account_id": a.id})
    db.commit()
    return {"invited": True, "email": a.email}


@router.get("/{case_id}/file.pdf")
def exit_file(case_id: int, ctx: Ctx = Depends(require("hr", "legal")), db: Session = Depends(get_db)):
    c = _case(db, ctx, case_id)
    try:
        pdf = reports.exit_file_pdf(db, ctx, c)
    except documents.PdfUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    audit.record(db, ctx, "exit_case", c.id, "exit_file_pdf")
    db.commit()
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="exit-file-{c.id}.pdf"'})

