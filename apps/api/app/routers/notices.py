from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, notices
from app.auth import token_hash
from app.crypto import decrypt_str
from app.db import get_db
from app.deps import Ctx, client_ip, require
from app.models import (
    Acknowledgement,
    Employee,
    ExitCase,
    NoticeBatch,
    NoticeDraft,
    NoticeMessage,
    NoticeTemplate,
    Org,
    Plan,
    utcnow,
)
from app.schemas import BatchIn, DecisionIn, DraftPatch, DraftsIn, ExcludeIn, TemplatePatch
from app.serialize import to_dict
from app.workflow import approvals

router = APIRouter(tags=["notices"])
VIEW = require("hr", "legal", "approver")
HR = require("hr")
LEGAL = require("legal")
BATCH_ACTORS = require("hr", "legal", "approver")


def _template(db: Session, ctx: Ctx, tid: int) -> NoticeTemplate:
    t = db.scalar(select(NoticeTemplate).where(NoticeTemplate.id == tid, NoticeTemplate.org_id == ctx.org_id))
    if t is None:
        raise HTTPException(404, "Template not found")
    return t


def _draft(db: Session, ctx: Ctx, did: int) -> NoticeDraft:
    d = db.scalar(select(NoticeDraft).where(NoticeDraft.id == did, NoticeDraft.org_id == ctx.org_id))
    if d is None:
        raise HTTPException(404, "Draft not found")
    return d


def _template_out(t: NoticeTemplate) -> dict:
    return to_dict(t, merge_fields=notices.merge_field_names(t))


def _draft_out(db: Session, d: NoticeDraft, with_body: bool = True) -> dict:
    case = db.get(ExitCase, d.exit_case_id)
    e = db.get(Employee, case.employee_id)
    t = db.get(NoticeTemplate, d.template_id)
    return to_dict(d, body=notices.draft_body(d) if with_body else None, employee_code=e.employee_code,
                   full_name=e.full_name, template={"id": t.id, "title": t.title, "version": t.version,
                                                    "status": t.status, "type": t.type})


# ------------------------------------------------------------------ templates
@router.get("/notice-templates")
def list_templates(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    rows = db.scalars(select(NoticeTemplate).where(NoticeTemplate.org_id == ctx.org_id)
                      .order_by(NoticeTemplate.key, NoticeTemplate.version.desc())).all()
    return [_template_out(t) for t in rows]


@router.get("/notice-templates/{template_id}")
def get_template(template_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    t = _template(db, ctx, template_id)
    versions = db.scalars(select(NoticeTemplate).where(NoticeTemplate.org_id == ctx.org_id,
                                                       NoticeTemplate.key == t.key)
                          .order_by(NoticeTemplate.version.desc())).all()
    sample = {k: f"[{k}]" for k in notices.merge_field_names(t)}
    sample |= {"pay_in_lieu": False, "can_appeal": True}
    subject, body, _ = notices.render_template(t, sample, {})
    return {"template": _template_out(t), "versions": [_template_out(v) for v in versions],
            "preview": {"subject": subject, "body": body}}


@router.patch("/notice-templates/{template_id}")
def edit_template(template_id: int, body: TemplatePatch, ctx: Ctx = Depends(require("hr", "legal")),
                  db: Session = Depends(get_db)):
    t = _template(db, ctx, template_id)
    if t.status == "retired":
        raise HTTPException(409, "Retired versions can't be edited")
    nt = notices.new_template_version(db, ctx, t, body.model_dump(exclude_unset=True))
    db.commit()
    return _template_out(nt)


@router.post("/notice-templates/{template_id}/approve")
def approve_template(template_id: int, ctx: Ctx = Depends(LEGAL), db: Session = Depends(get_db)):
    t = _template(db, ctx, template_id)
    if t.status != "draft":
        raise HTTPException(409, f"Template is {t.status}")
    if t.created_by == ctx.user:
        raise HTTPException(403, "Whoever wrote a template version can't approve it")
    for old in db.scalars(select(NoticeTemplate).where(NoticeTemplate.org_id == ctx.org_id, NoticeTemplate.key == t.key,
                                                       NoticeTemplate.status == "legal_approved")):
        old.status = "retired"
    t.status, t.approved_by, t.approved_at = "legal_approved", ctx.user, utcnow()
    audit.record(db, ctx, "template", t.id, "legal_approve", {"status": "draft"},
                 {"status": "legal_approved", "key": t.key, "version": t.version,
                  "content_hash": notices.template_hash(t)})
    db.commit()
    return _template_out(t)


# ------------------------------------------------------------------ drafts
@router.post("/plans/{plan_id}/notice-drafts", status_code=201)
def draft_for_plan(plan_id: int, body: DraftsIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.org_id == ctx.org_id))
    if p is None:
        raise HTTPException(404, "Plan not found")
    t = _template(db, ctx, body.template_id)
    if t.status == "retired":
        raise HTTPException(409, "That template version is retired")
    q = select(ExitCase).where(ExitCase.plan_id == p.id, ExitCase.state.not_in(("withdrawn", "closed")))
    if body.case_ids:
        q = q.where(ExitCase.id.in_(body.case_ids))
    cases = db.scalars(q).all()
    if not cases:
        raise HTTPException(409, "No exit cases to draft for")
    out = []
    for c in cases:
        if c.state == "on_hold" and t.type in notices.TERMINATION_TYPES:
            continue
        out.append(notices.create_draft(db, ctx, c, t))
    db.commit()
    return [_draft_out(db, d, with_body=False) for d in out]


@router.get("/notice-drafts")
def list_drafts(status: str | None = None, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    q = select(NoticeDraft).where(NoticeDraft.org_id == ctx.org_id)
    q = q.where(NoticeDraft.status == status) if status else q.where(NoticeDraft.status != "superseded")
    return [_draft_out(db, d, with_body=False) for d in db.scalars(q.order_by(NoticeDraft.id.desc()))]


@router.get("/notice-drafts/{draft_id}")
def get_draft(draft_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    d = _draft(db, ctx, draft_id)
    audit.record(db, ctx, "notice_draft", d.id, "view", None, {"exit_case_id": d.exit_case_id})
    db.commit()
    return _draft_out(db, d)


@router.patch("/notice-drafts/{draft_id}")
def edit_draft(draft_id: int, body: DraftPatch, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    nd = notices.edit_draft(db, ctx, _draft(db, ctx, draft_id), body.subject, body.body)
    db.commit()
    return _draft_out(db, nd)


# ------------------------------------------------------------------ batches
def _batch_out(db: Session, ctx: Ctx, b: NoticeBatch, with_messages: bool = True) -> dict:
    msgs = notices.batch_messages(db, b, include_tests=True)
    acks = set(db.scalars(select(Acknowledgement.message_id).where(
        Acknowledgement.message_id.in_([m.id for m in msgs] or [0]))))
    real = [m for m in msgs if not m.is_test]
    step = approvals.current_step(db, ctx.org_id, "notice_batch", b.id)
    out = to_dict(b, counts={
        "messages": sum(1 for m in real if not m.excluded), "excluded": sum(1 for m in real if m.excluded),
        **{s: sum(1 for m in real if m.status == s) for s in ("pending", "queued", "sent", "delivered", "bounced",
                                                              "failed", "cancelled")},
        "acknowledged": sum(1 for m in real if m.id in acks), "tests": sum(1 for m in msgs if m.is_test)},
        problems=notices.blocking_problems(db, b) if b.status in ("draft", "pending_approval", "approved") else [],
        current_step={"step": step.step, "roles": step.roles} if step else None,
        approvals=[to_dict(a) for a in approvals.history(db, ctx.org_id, "notice_batch", b.id)])
    if with_messages:
        out["messages"] = []
        for m in msgs:
            e = db.get(Employee, m.employee_id)
            out["messages"].append(to_dict(m, employee_code=e.employee_code, full_name=e.full_name,
                                           acknowledged=m.id in acks))
    return out


@router.get("/notice-batches")
def list_batches(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    return [_batch_out(db, ctx, b, with_messages=False)
            for b in db.scalars(select(NoticeBatch).where(NoticeBatch.org_id == ctx.org_id).order_by(NoticeBatch.id.desc()))]


@router.post("/notice-batches", status_code=201)
def create_batch(body: BatchIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    b = notices.create_batch(db, ctx, body.name, body.draft_ids)
    db.commit()
    return _batch_out(db, ctx, b)


@router.get("/notice-batches/{batch_id}")
def get_batch(batch_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    return _batch_out(db, ctx, notices.get_batch(db, ctx, batch_id))


@router.get("/notice-batches/{batch_id}/messages/{message_id}")
def preview_message(batch_id: int, message_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    m = db.scalar(select(NoticeMessage).where(NoticeMessage.id == message_id, NoticeMessage.batch_id == b.id))
    if m is None:
        raise HTTPException(404, "Message not found")
    audit.record(db, ctx, "notice_message", m.id, "view", None, {"exit_case_id": m.exit_case_id})
    db.commit()
    return to_dict(m, body=decrypt_str(m.body_enc))


@router.post("/notice-batches/{batch_id}/exclude")
def exclude(batch_id: int, body: ExcludeIn, ctx: Ctx = Depends(BATCH_ACTORS), db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    notices.set_excluded(db, ctx, b, body.message_id, body.excluded)
    db.commit()
    return _batch_out(db, ctx, b)


@router.post("/notice-batches/{batch_id}/submit")
def submit(batch_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    notices.submit_batch(db, ctx, b)
    db.commit()
    return _batch_out(db, ctx, b)


@router.post("/notice-batches/{batch_id}/approve")
def approve(batch_id: int, body: DecisionIn, ctx: Ctx = Depends(require("legal", "approver")),
            db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    notices.decide_batch(db, ctx, b, body.approve, body.comment)
    db.commit()
    return _batch_out(db, ctx, b)


@router.post("/notice-batches/{batch_id}/test-send")
def test_send(batch_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    n = notices.test_send(db, ctx, b)
    db.commit()
    return {"queued": n, "batch": _batch_out(db, ctx, b, with_messages=False)}


@router.post("/notice-batches/{batch_id}/release")
def release(batch_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    b = notices.get_batch(db, ctx, batch_id)
    n = notices.release(db, ctx, b)
    db.commit()
    return {"queued": n, "batch": _batch_out(db, ctx, b, with_messages=False)}


@router.get("/notice-messages")
def list_messages(status: str | None = None, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    q = select(NoticeMessage).where(NoticeMessage.org_id == ctx.org_id, NoticeMessage.is_test.is_(False))
    if status:
        q = q.where(NoticeMessage.status == status)
    msgs = db.scalars(q.order_by(NoticeMessage.id.desc()).limit(500)).all()
    acks = {a.message_id: a.acknowledged_at for a in db.scalars(select(Acknowledgement).where(
        Acknowledgement.message_id.in_([m.id for m in msgs] or [0])))}
    out = []
    for m in msgs:
        e = db.get(Employee, m.employee_id)
        out.append(to_dict(m, employee_code=e.employee_code, full_name=e.full_name, acknowledged_at=acks.get(m.id)))
    return out


# ------------------------------------------------------------------ employee acknowledgement (public, by token)
def _by_token(db: Session, token: str) -> NoticeMessage:
    m = db.scalar(select(NoticeMessage).where(NoticeMessage.ack_token_hash == token_hash(token)))
    if m is None:
        raise HTTPException(404, "This link isn't valid")
    return m


@router.get("/acknowledge/{token}")
def ack_info(token: str, db: Session = Depends(get_db)):
    m = _by_token(db, token)
    org = db.get(Org, m.org_id)
    done = db.scalar(select(Acknowledgement).where(Acknowledgement.message_id == m.id))
    return {"subject": m.subject, "company": (org.settings or {}).get("legal_name", org.name),
            "acknowledged_at": done.acknowledged_at if done else None}


@router.post("/acknowledge/{token}")
def acknowledge(token: str, request: Request, db: Session = Depends(get_db)):
    m = _by_token(db, token)
    done = db.scalar(select(Acknowledgement).where(Acknowledgement.message_id == m.id))
    if done:
        return {"acknowledged_at": done.acknowledged_at}
    a = Acknowledgement(org_id=m.org_id, message_id=m.id, employee_id=m.employee_id, ip=client_ip(request))
    db.add(a)
    db.flush()
    e = db.get(Employee, m.employee_id)
    audit.record_raw(db, m.org_id, f"employee:{e.employee_code}", "notice_message", m.id, "acknowledged", None,
                     {"exit_case_id": m.exit_case_id})
    db.commit()
    return {"acknowledged_at": a.acknowledged_at}

