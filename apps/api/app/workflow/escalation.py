"""Escalate approval steps that have waited too long (default 3 days, org setting escalation_days)."""

from datetime import timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval, Notification, Org, QueueJob, utcnow
from app.notify import notify_roles
from app.workflow.approvals import LINKS
from app.worker import handler


@handler("escalate_approvals")
def escalate(db: Session, job: QueueJob) -> None:
    org = db.get(Org, job.org_id)
    days = int((org.settings or {}).get("escalation_days", 3))
    cutoff = utcnow() - timedelta(days=days)
    for a in db.scalars(select(Approval).where(Approval.org_id == org.id, Approval.status == "pending")):
        created = a.created_at if a.created_at.tzinfo else a.created_at.replace(tzinfo=timezone.utc)
        link = LINKS[a.entity_type].format(id=a.entity_id)
        already = db.scalar(select(Notification.id).where(Notification.org_id == org.id,
                                                          Notification.kind == "escalation", Notification.link == link))
        if created <= cutoff and already is None:
            notify_roles(db, org.id, [*a.roles, "admin"], "escalation",
                         f"An approval has been waiting more than {days} days",
                         link)
