"""Worker handler that sends one notice message: throttled, retried, tracked, and audited."""

import secrets
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, documents, storage
from app.auth import token_hash
from app.compliance.rules import rulebook
from app.config import MAIL_RATE_PER_MINUTE, WEB_BASE_URL
from app.deps import Ctx
from app.exits import notice_period, states
from app.exits.tasks import add_task
from app.mail import OutMail, send
from app.models import (
    Document,
    Employee,
    ExitCase,
    NoticeDraft,
    NoticeMessage,
    NoticeTemplate,
    Plan,
    QueueJob,
    utcnow,
)
from app.notices import ACK_PLACEHOLDER, TERMINATION_TYPES, draft_body
from app.notify import notify_roles
from app.queue import Retry
from app.worker import handler

SYSTEM = "system:sender"


def _system_ctx(org_id: int) -> Ctx:
    return Ctx(org_id=org_id, user_id=None, user=SYSTEM, role="admin")


def _throttled(db: Session, org_id: int) -> bool:
    since = utcnow() - timedelta(seconds=60)
    sent = db.scalar(select(func.count()).select_from(NoticeMessage).where(
        NoticeMessage.org_id == org_id, NoticeMessage.sent_at >= since))
    return sent >= MAIL_RATE_PER_MINUTE


def _attachment(db: Session, ctx: Ctx, t: NoticeTemplate, case: ExitCase, body: str, is_test: bool
                ) -> tuple[str, bytes] | None:
    """The PDF to attach: an issued FNF/relieving/experience document, or the letter itself.
    Real sends store the letter as a sealed document; test sends don't store anything."""
    linked_kind = {"fnf_cover": "fnf_statement", "relieving_letter_cover": "relieving_letter",
                   "experience_letter_cover": "experience_letter"}.get(t.key)
    if linked_kind:
        doc = db.scalar(select(Document).where(Document.exit_case_id == case.id, Document.kind == linked_kind)
                        .order_by(Document.version.desc()))
        if doc is None and linked_kind == "fnf_statement" and not is_test:
            doc = documents.issue_for_case(db, ctx, case, "fnf_statement")
        if doc is None:
            if is_test:
                return None
            raise RuntimeError(f"{linked_kind} has not been issued")
        return f"{doc.title}.pdf", storage.load(doc.storage_key)
    if not t.attach_pdf:
        return None
    pdf = documents.letter_pdf(db, ctx, case, t.title, body.replace(ACK_PLACEHOLDER, "(link in the email)"))
    if not is_test:
        kind = {"notice of termination": "termination_letter",
                "notice of role elimination": "role_elimination_notice"}.get(t.type, "notice_letter")
        documents.store(db, ctx, kind, t.title, pdf, case.employee_id, case.id)
    return f"{t.title}.pdf", pdf


@handler("send_message")
def send_message(db: Session, job: QueueJob) -> None:
    m = db.get(NoticeMessage, job.payload["message_id"])
    if m is None or m.status not in ("queued",):
        return  # cancelled or already handled
    if _throttled(db, m.org_id):
        raise Retry(after_seconds=10)

    ctx = _system_ctx(m.org_id)
    d = db.get(NoticeDraft, m.draft_id)
    t = db.get(NoticeTemplate, d.template_id)
    case = db.get(ExitCase, m.exit_case_id)
    if not m.is_test and (case.state == "withdrawn" or (case.state == "on_hold" and t.type in TERMINATION_TYPES)):
        m.status, m.last_error = "cancelled", f"case {case.state}"
        return

    body = draft_body(d)
    if m.is_test:
        text = ("TEST · This is a test send to an internal address. It was not sent to the employee.\n\n"
                + body.replace(ACK_PLACEHOLDER, f"{WEB_BASE_URL}/ack/TEST"))
    else:
        token = secrets.token_urlsafe(24)
        m.ack_token_hash = token_hash(token)
        text = body.replace(ACK_PLACEHOLDER, f"{WEB_BASE_URL}/ack/{token}")

    attachments = []
    password = None
    att = _attachment(db, ctx, t, case, body, m.is_test)
    if att:
        name, data = att
        if t.encrypt_attachment and not m.is_test:
            password = documents.new_password()
            data = documents.protect(data, password)
        attachments.append((name if not m.is_test else f"TEST - {name}", data, "application/pdf"))

    m.attempts += 1
    res = send(db, OutMail(org_id=m.org_id, to=m.to_addresses, subject=m.subject, text=text, attachments=attachments))
    if res.status == "failed":
        m.last_error = res.error
        if job.attempts + 1 >= job.max_attempts:
            m.status = "failed"
            audit.record(db, ctx, "notice_message", m.id, "failed", None,
                         {"exit_case_id": case.id, "error": res.error})
            add_task(db, case, "resend_failed", "A notice could not be sent; check and resend", "hr")
            return
        raise RuntimeError(res.error or "temporary send failure")

    m.sent_at = utcnow()
    if res.status == "bounced":
        m.status, m.last_error = "bounced", res.error
        audit.record(db, ctx, "notice_message", m.id, "bounced", None, {"exit_case_id": case.id})
        if not m.is_test:
            add_task(db, case, "resolve_contact", "A notice bounced: confirm the employee's email and resend", "hr")
            notify_roles(db, m.org_id, ["hr"], "bounce", "A notice bounced and needs a corrected address",
                         f"/cases/{case.id}")
        return
    m.status = "delivered" if res.status == "delivered" else "sent"
    m.delivered_at = utcnow() if res.status == "delivered" else None
    audit.record(db, ctx, "notice_message", m.id, "sent" if not m.is_test else "test_sent", None,
                 {"exit_case_id": case.id, "content_hash": m.content_hash, "to_count": len(m.to_addresses),
                  "attachments": len(attachments), "password_protected": bool(password)})
    if password:
        send(db, OutMail(org_id=m.org_id, to=m.to_addresses, subject=f"Password for: {m.subject}",
                         text="The attached document in our previous message is password protected.\n\n"
                              f"Password: {password}\n\nThis password is sent separately for your security."))
    d.status = "sent" if not m.is_test else d.status

    if not m.is_test and t.type in TERMINATION_TYPES:
        _after_notice_sent(db, ctx, case)


def _after_notice_sent(db: Session, ctx: Ctx, case: ExitCase) -> None:
    e = db.get(Employee, case.employee_id)
    plan = db.get(Plan, case.plan_id)
    if not case.notice_date:
        case.notice_date = date.today()
    if case.last_working_day is None:
        r = notice_period.compute(e, rulebook(db, case.org_id, plan.ruleset_id), case.notice_date, case.pay_in_lieu)
        case.notice_days, case.last_working_day, case.lwd_trace = r.days, r.last_working_day, {"steps": r.trace}
    if case.state != "on_hold":
        states.advance(db, ctx, case, "notice_sent")
        e.status = "on_notice"
        if case.pay_in_lieu or not case.notice_days:
            states.advance(db, ctx, case, "last_day_set")
        else:
            states.advance(db, ctx, case, "notice_period")
