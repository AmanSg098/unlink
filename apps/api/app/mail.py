"""Outgoing mail through a provider adapter.

Development and tests always use the capture provider: messages are stored in `captured_mail` and
shown at http://localhost:8025, never delivered. Live delivery needs APP_ENV=staging|production and
MAIL_PROVIDER=smtp|ses (SES through its SMTP interface).

Capture simulates a hard bounce for any address at bounce.invalid, so bounce handling can be tested.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import (
    MAIL_FROM,
    MAIL_PROVIDER,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_STARTTLS,
    SMTP_USER,
    live_mail_allowed,
)
from app.models import CapturedMail

log = logging.getLogger(__name__)
BOUNCE_DOMAIN = "bounce.invalid"


@dataclass
class OutMail:
    org_id: int
    to: list[str]
    subject: str
    text: str
    attachments: list[tuple[str, bytes, str]] = field(default_factory=list)  # (filename, data, mime)


@dataclass
class SendResult:
    status: str  # delivered | sent | bounced | failed
    error: str | None = None
    temporary: bool = False


def provider_name() -> str:
    return MAIL_PROVIDER if live_mail_allowed() else "capture"


def send(db: Session, mail: OutMail) -> SendResult:
    provider = provider_name()
    if provider == "capture":
        return _capture(db, mail)
    return _smtp(mail)


def _capture(db: Session, mail: OutMail) -> SendResult:
    if any(a.lower().endswith("@" + BOUNCE_DOMAIN) for a in mail.to):
        return SendResult("bounced", "550 mailbox unavailable (simulated)")
    db.add(CapturedMail(org_id=mail.org_id, to=mail.to, subject=mail.subject, text=mail.text,
                        attachments=[{"filename": n, "size": len(d), "mime": m} for n, d, m in mail.attachments]))
    return SendResult("delivered")


def _smtp(mail: OutMail) -> SendResult:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = MAIL_FROM, ", ".join(mail.to), mail.subject
    msg.set_content(mail.text)
    for name, data, mime in mail.attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            if SMTP_STARTTLS:
                s.starttls()
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD or "")
            s.send_message(msg)
        return SendResult("sent")
    except smtplib.SMTPRecipientsRefused as exc:
        return SendResult("bounced", str(exc)[:300])
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("smtp send failed: %s", type(exc).__name__)
        return SendResult("failed", type(exc).__name__, temporary=True)
