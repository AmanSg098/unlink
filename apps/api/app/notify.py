"""Staff notifications: in-app items plus optional email. Content never includes employee names or amounts;
it says what kind of item needs attention and links to it."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import WEB_BASE_URL
from app.integrations import enabled_integration
from app.mail import OutMail, send
from app.models import Notification, QueueJob, User
from app.queue import enqueue
from app.worker import handler


def notify_users(db: Session, org_id: int, users: list[User], kind: str, title: str, link: str,
                 email: bool = True) -> None:
    if users and enabled_integration(db, org_id, "messaging"):
        enqueue(db, org_id, "messaging_notify", {"text": f"{title}: {WEB_BASE_URL}{link}"})
    for u in users:
        db.add(Notification(org_id=org_id, user_id=u.id, kind=kind, title=title, link=link))
        if email and u.notify_email:
            enqueue(db, org_id, "staff_email", {"to": u.email, "subject": f"Unlink: {title}",
                                                "text": f"{title}\n\nOpen it in Unlink: {WEB_BASE_URL}{link}\n"})


def notify_roles(db: Session, org_id: int, roles: list[str], kind: str, title: str, link: str,
                 exclude: tuple[str, ...] = (), email: bool = True) -> None:
    users = [u for u in db.scalars(select(User).where(User.org_id == org_id, User.active.is_(True),
                                                      User.role.in_(roles)))
             if u.email not in exclude]
    notify_users(db, org_id, users, kind, title, link, email)


@handler("staff_email")
def _send_staff_email(db: Session, job: QueueJob) -> None:
    p = job.payload
    res = send(db, OutMail(org_id=job.org_id, to=[p["to"]], subject=p["subject"], text=p["text"]))
    if res.status == "failed":
        raise RuntimeError(res.error or "send failed")
