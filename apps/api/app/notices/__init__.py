"""Notices and communications: templates, per-employee drafts, batches, approval by content hash, release.

Sending itself happens in the worker (notices/sending.py). Nothing reaches an employee unless the batch was
approved with the exact content hash of each message and then released by HR.
"""

from datetime import date, timedelta
from pathlib import Path

import yaml
from fastapi import HTTPException
from jinja2 import meta
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.config import TEMPLATES_DIR
from app.crypto import content_hash, decrypt_str, encrypt_str
from app.deps import Ctx
from app.exits import states
from app.models import (
    Employee,
    ExitCase,
    FnfStatement,
    NoticeBatch,
    NoticeDraft,
    NoticeMessage,
    NoticeTemplate,
    Org,
    Plan,
    PlanResult,
    utcnow,
)
from app.queue import enqueue
from app.reasons import evidence_status, protected_terms_in, wording
from app.workflow import approvals

ACK_PLACEHOLDER = "[[ACK_LINK]]"
TERMINATION_TYPES = {"notice of termination", "notice of role elimination"}
CONSULTATION_TYPE = "pre-notice consultation"
_env = SandboxedEnvironment(autoescape=False, keep_trailing_newline=True)


# ------------------------------------------------------------------ templates

def _read_template_file(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body.strip() + "\n"


def load_templates(db: Session, org_id: int, actor: str = "system") -> int:
    """Create any template from templates/notices that the org doesn't have yet (as draft, version 1)."""
    have = set(db.scalars(select(NoticeTemplate.key).where(NoticeTemplate.org_id == org_id)))
    added = 0
    for path in sorted((TEMPLATES_DIR / "notices").glob("*.md")):
        m, body = _read_template_file(path)
        if m["key"] in have:
            continue
        db.add(NoticeTemplate(org_id=org_id, key=m["key"], type=m["type"], title=m["title"], subject=m["subject"],
                              body=body, jurisdiction=m.get("jurisdiction", "india"),
                              send_to_personal=m.get("send_to_personal", False), attach_pdf=m.get("attach_pdf", True),
                              encrypt_attachment=m.get("encrypt_attachment", False), created_by=actor))
        added += 1
    db.flush()
    return added


def merge_field_names(t: NoticeTemplate) -> list[str]:
    names = set()
    for src in (t.subject, t.body):
        names |= meta.find_undeclared_variables(_env.parse(src))
    return sorted(names)


def current_template(db: Session, org_id: int, key: str) -> NoticeTemplate | None:
    return db.scalar(select(NoticeTemplate).where(NoticeTemplate.org_id == org_id, NoticeTemplate.key == key,
                                                  NoticeTemplate.status != "retired")
                     .order_by(NoticeTemplate.version.desc()).limit(1))


def template_hash(t: NoticeTemplate) -> str:
    return content_hash({"subject": t.subject, "body": t.body, "send_to_personal": t.send_to_personal,
                         "attach_pdf": t.attach_pdf, "encrypt_attachment": t.encrypt_attachment})


def new_template_version(db: Session, ctx: Ctx, t: NoticeTemplate, changes: dict) -> NoticeTemplate:
    """Editing an approved template creates a new draft version; the old one stays usable until replaced."""
    for k, v in changes.items():
        if k in ("subject", "body") and protected_terms_in(v):
            raise HTTPException(422, f"Text contains protected terms: {', '.join(protected_terms_in(v))}")
    if t.status == "draft":
        before = {k: getattr(t, k) for k in changes}
        for k, v in changes.items():
            setattr(t, k, v)
        audit.record(db, ctx, "template", t.id, "update", before, changes)
        return t
    nt = NoticeTemplate(org_id=t.org_id, key=t.key, type=t.type, title=t.title, subject=t.subject, body=t.body,
                        jurisdiction=t.jurisdiction, send_to_personal=t.send_to_personal, attach_pdf=t.attach_pdf,
                        encrypt_attachment=t.encrypt_attachment, version=t.version + 1, parent_id=t.id,
                        created_by=ctx.user, status="draft")
    for k, v in changes.items():
        setattr(nt, k, v)
    db.add(nt)
    db.flush()
    audit.record(db, ctx, "template", nt.id, "new_version", {"version": t.version}, {"version": nt.version, **changes})
    return nt


# ------------------------------------------------------------------ merge fields

def wording_approved(org: Org, code: str | None) -> bool:
    return bool(code) and code in ((org.settings or {}).get("reason_wording_approvals") or {})


def merge_values(db: Session, case: ExitCase, extra: dict | None = None) -> tuple[dict, dict[str, str]]:
    """Values for every merge field we know, plus explanations for any we can't fill yet."""
    org = db.get(Org, case.org_id)
    e = db.get(Employee, case.employee_id)
    plan = db.get(Plan, case.plan_id)
    s = org.settings or {}
    problems: dict[str, str] = {}
    vals = {
        "company_name": s.get("legal_name", org.name), "hr_contact": s.get("hr_contact_email"),
        "employee_name": e.full_name, "employee_code": e.employee_code, "role": e.role, "department": e.department,
        "location": e.location, "notice_date": case.notice_date.isoformat() if case.notice_date else None,
        "notice_days": case.notice_days, "pay_in_lieu": case.pay_in_lieu,
        "last_working_day": case.last_working_day.isoformat() if case.last_working_day else None,
        "ack_link": ACK_PLACEHOLDER, "reason_text": None, "payment_due_on": None,
    }
    if not vals["hr_contact"]:
        problems["hr_contact"] = "Set the HR contact email in organisation settings"
    if not case.notice_date:
        problems["notice_date"] = "Set the planned notice date on the case"
    if case.reason_code:
        approved_other = approvals.is_approved(db, case.org_id, "reason_other", case.id,
                                               reason_hash(case)) if case.reason_code == "OTHER" else True
        ev = evidence_status(db, case, e, plan, rulebook(db, case.org_id, plan.ruleset_id), approved_other)
        if not ev["ok"]:
            problems["reason_text"] = ev["missing"] or "Reason evidence is missing"
        elif not wording_approved(org, case.reason_code):
            problems["reason_text"] = f"Legal hasn't approved the wording for {case.reason_code}"
        else:
            vals["reason_text"] = wording(case, e)
    else:
        problems["reason_text"] = "Choose a reason code for the case"
    fnf = db.scalar(select(FnfStatement).where(FnfStatement.exit_case_id == case.id,
                                               FnfStatement.status.in_(("approved", "paid")))
                    .order_by(FnfStatement.version.desc()))
    if fnf and fnf.payment_due_on:
        vals["payment_due_on"] = fnf.payment_due_on.isoformat()
    else:
        problems["payment_due_on"] = "No approved FNF statement yet"
    vals |= extra or {}
    return vals, problems


def reason_hash(case: ExitCase) -> str:
    return content_hash({"code": case.reason_code, "detail": case.reason_detail, "version": case.reason_version})


def render_template(t: NoticeTemplate, vals: dict, problems: dict[str, str]) -> tuple[str, str, list[str]]:
    """Render subject and body. Fields without a value render as [MISSING: name] and are reported."""
    needed = merge_field_names(t)
    missing = [n for n in needed if vals.get(n) is None]
    filled = {n: (vals.get(n) if vals.get(n) is not None else f"[MISSING: {n}]") for n in needed}
    subject = _env.from_string(t.subject).render(**filled).strip()
    body = _env.from_string(t.body).render(**filled)
    return subject, body, [f"{n}: {problems.get(n, 'no value')}" for n in missing]


# ------------------------------------------------------------------ drafts

def draft_hash(d: NoticeDraft, body: str) -> str:
    return content_hash({"subject": d.subject, "body": body, "template_id": d.template_id,
                         "exit_case_id": d.exit_case_id, "version": d.version})


def create_draft(db: Session, ctx: Ctx, case: ExitCase, t: NoticeTemplate, extra: dict | None = None) -> NoticeDraft:
    # A hold pauses exit steps; messages about the hold itself (grievances) may still be prepared.
    if t.type in TERMINATION_TYPES or case.state in ("withdrawn", "closed"):
        states.require_active(case)
    vals, problems = merge_values(db, case, extra)
    subject, body, missing = render_template(t, vals, problems)
    prev = db.scalars(select(NoticeDraft).where(NoticeDraft.exit_case_id == case.id,
                                                NoticeDraft.template_id.in_(_template_family(db, t)),
                                                NoticeDraft.status == "draft")).all()
    for p in prev:
        p.status = "superseded"
    version = (db.scalar(select(func.max(NoticeDraft.version)).where(NoticeDraft.exit_case_id == case.id)) or 0) + 1
    d = NoticeDraft(org_id=ctx.org_id, exit_case_id=case.id, template_id=t.id, version=version, subject=subject,
                    body_enc=encrypt_str(body), merged_fields={k: vals.get(k) for k in merge_field_names(t)},
                    missing_fields=missing, flagged_terms=protected_terms_in(subject + "\n" + body),
                    content_hash="", created_by=ctx.user)
    d.content_hash = draft_hash(d, body)
    db.add(d)
    db.flush()
    audit.record(db, ctx, "notice_draft", d.id, "create", None,
                 {"exit_case_id": case.id, "template": t.key, "template_version": t.version, "version": version,
                  "content_hash": d.content_hash, "missing": len(missing), "flagged_terms": d.flagged_terms})
    if t.type in TERMINATION_TYPES:
        states.advance(db, ctx, case, "notice_drafted")
    return d


def _template_family(db: Session, t: NoticeTemplate) -> list[int]:
    return list(db.scalars(select(NoticeTemplate.id).where(NoticeTemplate.org_id == t.org_id,
                                                           NoticeTemplate.key == t.key)))


def edit_draft(db: Session, ctx: Ctx, d: NoticeDraft, subject: str, body: str) -> NoticeDraft:
    if d.status not in ("draft", "in_batch"):
        raise HTTPException(409, f"This draft is {d.status}")
    case = db.get(ExitCase, d.exit_case_id)
    if db.get(NoticeTemplate, d.template_id).type in TERMINATION_TYPES:
        states.require_active(case)
    nd = NoticeDraft(org_id=d.org_id, exit_case_id=d.exit_case_id, template_id=d.template_id, version=d.version + 1,
                     subject=subject.strip(), body_enc=encrypt_str(body), merged_fields=d.merged_fields,
                     missing_fields=[m for m in d.missing_fields if f"[MISSING: {m.split(':')[0]}]" in body],
                     flagged_terms=protected_terms_in(subject + "\n" + body), content_hash="", created_by=ctx.user,
                     status=d.status)
    nd.content_hash = draft_hash(nd, body)
    d.status = "superseded"
    db.add(nd)
    db.flush()
    # A draft already in a batch: point its pending message at the new version. The batch's hash changes,
    # so any approval it had no longer matches and the batch must be approved again.
    for m in db.scalars(select(NoticeMessage).where(NoticeMessage.draft_id == d.id, NoticeMessage.is_test.is_(False),
                                                    NoticeMessage.status == "pending")):
        m.draft_id, m.subject, m.body_enc, m.content_hash = nd.id, nd.subject, nd.body_enc, nd.content_hash
        batch = db.get(NoticeBatch, m.batch_id)
        if batch.status in ("pending_approval", "approved"):
            batch.status = "draft"
    audit.record(db, ctx, "notice_draft", nd.id, "edit", {"version": d.version, "content_hash": d.content_hash},
                 {"version": nd.version, "content_hash": nd.content_hash, "exit_case_id": nd.exit_case_id})
    return nd


def draft_body(d: NoticeDraft) -> str:
    return decrypt_str(d.body_enc)


# ------------------------------------------------------------------ batches

def get_batch(db: Session, ctx: Ctx, batch_id: int) -> NoticeBatch:
    b = db.scalar(select(NoticeBatch).where(NoticeBatch.id == batch_id, NoticeBatch.org_id == ctx.org_id))
    if b is None:
        raise HTTPException(404, "Batch not found")
    return b


def batch_messages(db: Session, b: NoticeBatch, include_tests: bool = False) -> list[NoticeMessage]:
    q = select(NoticeMessage).where(NoticeMessage.batch_id == b.id)
    if not include_tests:
        q = q.where(NoticeMessage.is_test.is_(False))
    return list(db.scalars(q.order_by(NoticeMessage.id)))


def batch_hash(db: Session, b: NoticeBatch) -> str:
    return content_hash(sorted((m.id, m.content_hash, m.excluded) for m in batch_messages(db, b)))


def recipients(e: Employee, t: NoticeTemplate) -> list[str]:
    to = [a for a in [e.email] if a]
    if (t.send_to_personal or not to) and e.personal_email:
        to.append(e.personal_email)
    return to


def create_batch(db: Session, ctx: Ctx, name: str, draft_ids: list[int]) -> NoticeBatch:
    drafts = list(db.scalars(select(NoticeDraft).where(NoticeDraft.org_id == ctx.org_id, NoticeDraft.id.in_(draft_ids))))
    if not drafts or len(drafts) != len(set(draft_ids)):
        raise HTTPException(404, "One or more drafts were not found")
    bad = [d.id for d in drafts if d.status != "draft"]
    if bad:
        raise HTTPException(409, f"Drafts already used or superseded: {bad}")
    b = NoticeBatch(org_id=ctx.org_id, name=name, created_by=ctx.user)
    db.add(b)
    db.flush()
    for d in drafts:
        case = db.get(ExitCase, d.exit_case_id)
        e = db.get(Employee, case.employee_id)
        t = db.get(NoticeTemplate, d.template_id)
        db.add(NoticeMessage(org_id=ctx.org_id, batch_id=b.id, draft_id=d.id, exit_case_id=case.id, employee_id=e.id,
                             to_addresses=recipients(e, t), subject=d.subject, body_enc=d.body_enc,
                             content_hash=d.content_hash))
        d.status = "in_batch"
    db.flush()
    audit.record(db, ctx, "notice_batch", b.id, "create", None, {"drafts": draft_ids, "count": len(drafts)})
    return b


def blocking_problems(db: Session, b: NoticeBatch) -> list[str]:
    """Anything that must be fixed before the batch can be approved or released."""
    out = []
    for m in batch_messages(db, b):
        if m.excluded:
            continue
        d = db.get(NoticeDraft, m.draft_id)
        t = db.get(NoticeTemplate, d.template_id)
        e = db.get(Employee, m.employee_id)
        case = db.get(ExitCase, m.exit_case_id)
        tag = f"{e.employee_code}"
        if t.status != "legal_approved":
            out.append(f"{tag}: template '{t.title}' v{t.version} isn't legal-approved")
        for f in d.missing_fields:
            out.append(f"{tag}: missing {f}")
        if d.flagged_terms:
            out.append(f"{tag}: protected terms in text ({', '.join(d.flagged_terms)})")
        if not m.to_addresses:
            out.append(f"{tag}: no email address")
        if case.state in ("withdrawn", "closed") or (case.state == "on_hold" and t.type in TERMINATION_TYPES):
            out.append(f"{tag}: case is {case.state}")
    return out


def submit_batch(db: Session, ctx: Ctx, b: NoticeBatch) -> None:
    if b.status not in ("draft",):
        raise HTTPException(409, f"Batch is {b.status}")
    if not [m for m in batch_messages(db, b) if not m.excluded]:
        raise HTTPException(422, "The batch has no messages to send")
    problems = blocking_problems(db, b)
    if problems:
        raise HTTPException(422, "; ".join(problems[:10]))
    approvals.start(db, ctx, "notice_batch", b.id, batch_hash(db, b))
    b.status = "pending_approval"


def decide_batch(db: Session, ctx: Ctx, b: NoticeBatch, approve: bool, comment: str | None) -> None:
    if b.status != "pending_approval":
        raise HTTPException(409, f"Batch is {b.status}")
    drafters = {db.get(NoticeDraft, m.draft_id).created_by for m in batch_messages(db, b)}
    forbidden = {who: "You drafted a notice in this batch, so you can't approve sending it" for who in drafters}
    _, finished = approvals.decide(db, ctx, "notice_batch", b.id, approve, comment, batch_hash(db, b), forbidden)
    if not approve:
        b.status = "draft"
        return
    if finished:
        b.status = "approved"
        for m in batch_messages(db, b):
            if not m.excluded:
                case = db.get(ExitCase, m.exit_case_id)
                t = db.get(NoticeTemplate, db.get(NoticeDraft, m.draft_id).template_id)
                if t.type in TERMINATION_TYPES and case.state not in ("on_hold",):
                    states.advance(db, ctx, case, "notice_approved")


def set_excluded(db: Session, ctx: Ctx, b: NoticeBatch, message_id: int, excluded: bool) -> None:
    if b.status not in ("draft", "pending_approval"):
        raise HTTPException(409, "Items can only be excluded before the batch is approved")
    m = db.scalar(select(NoticeMessage).where(NoticeMessage.id == message_id, NoticeMessage.batch_id == b.id,
                                              NoticeMessage.is_test.is_(False)))
    if m is None:
        raise HTTPException(404, "Message not in this batch")
    m.excluded = excluded
    if b.status == "pending_approval":
        b.status = "draft"  # the approval round no longer matches; resubmit
    audit.record(db, ctx, "notice_batch", b.id, "exclude" if excluded else "include", None,
                 {"message_id": message_id, "excluded": excluded})


def test_send(db: Session, ctx: Ctx, b: NoticeBatch) -> int:
    addresses = (db.get(Org, ctx.org_id).settings or {}).get("test_addresses") or []
    if not addresses:
        raise HTTPException(422, "Set internal test addresses in organisation settings first")
    n = 0
    for m in batch_messages(db, b):
        if m.excluded:
            continue
        tm = NoticeMessage(org_id=ctx.org_id, batch_id=b.id, draft_id=m.draft_id, exit_case_id=m.exit_case_id,
                           employee_id=m.employee_id, is_test=True, to_addresses=list(addresses),
                           subject=f"[TEST] {m.subject}", body_enc=m.body_enc, content_hash=m.content_hash,
                           status="queued")
        db.add(tm)
        db.flush()
        enqueue(db, ctx.org_id, "send_message", {"message_id": tm.id})
        n += 1
    b.test_sent_at = utcnow()
    audit.record(db, ctx, "notice_batch", b.id, "test_send", None, {"messages": n, "to": addresses})
    return n


def release(db: Session, ctx: Ctx, b: NoticeBatch, today: date | None = None) -> int:
    today = today or date.today()
    if b.status != "approved":
        raise HTTPException(409, f"Batch is {b.status}; it must be approved before release")
    if not approvals.is_approved(db, ctx.org_id, "notice_batch", b.id, batch_hash(db, b)):
        raise HTTPException(409, "Messages changed after approval; the batch must be approved again")
    problems = blocking_problems(db, b)
    msgs = [m for m in batch_messages(db, b) if not m.excluded]
    for m in msgs:
        case = db.get(ExitCase, m.exit_case_id)
        e = db.get(Employee, m.employee_id)
        t = db.get(NoticeTemplate, db.get(NoticeDraft, m.draft_id).template_id)
        if t.type in TERMINATION_TYPES:
            if case.notice_date and case.notice_date < today:
                problems.append(f"{e.employee_code}: the planned notice date {case.notice_date} has passed; redraft")
            consult = rulebook(db, ctx.org_id, db.get(Plan, case.plan_id).ruleset_id).value("IN-CONSULT-001") or {}
            group = db.scalar(select(func.count()).select_from(PlanResult).where(
                PlanResult.plan_id == case.plan_id, PlanResult.final_selected.is_(True)))
            if consult and group >= consult.get("min_group_size", 10**9):
                cutoff = today - timedelta(days=consult["days_before_notice"])
                done = db.scalar(select(func.count()).select_from(NoticeMessage)
                                 .join(NoticeDraft, NoticeDraft.id == NoticeMessage.draft_id)
                                 .join(NoticeTemplate, NoticeTemplate.id == NoticeDraft.template_id)
                                 .where(NoticeMessage.exit_case_id == case.id, NoticeMessage.is_test.is_(False),
                                        NoticeTemplate.type == CONSULTATION_TYPE,
                                        NoticeMessage.status.in_(("sent", "delivered")),
                                        func.date(NoticeMessage.sent_at) <= cutoff))
                if not done:
                    problems.append(f"{e.employee_code}: consultation must be sent at least "
                                    f"{consult['days_before_notice']} days before a termination notice (IN-CONSULT-001)")
    if problems:
        raise HTTPException(409, "; ".join(problems[:10]))
    for m in msgs:
        m.status = "queued"
        enqueue(db, ctx.org_id, "send_message", {"message_id": m.id})
    b.status, b.released_by, b.released_at = "released", ctx.user, utcnow()
    audit.record(db, ctx, "notice_batch", b.id, "release", None,
                 {"messages": len(msgs), "content_hashes": [m.content_hash for m in msgs]})
    return len(msgs)


def cancel_unsent_for_case(db: Session, case: ExitCase) -> int:
    n = 0
    for m in db.scalars(select(NoticeMessage).where(NoticeMessage.exit_case_id == case.id,
                                                    NoticeMessage.status.in_(("pending", "queued")))):
        m.status = "cancelled"
        n += 1
    for d in db.scalars(select(NoticeDraft).where(NoticeDraft.exit_case_id == case.id,
                                                  NoticeDraft.status.in_(("draft", "in_batch")))):
        d.status = "superseded"
    return n

