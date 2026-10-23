"""Weekly summary to HR Ops: counts only (no names or amounts), with links."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Approval, ExitCase, ExitTask, NoticeMessage, QueueJob
from app.notify import notify_roles
from app.worker import handler


@handler("weekly_report")
def weekly_report(db: Session, job: QueueJob) -> None:
    org = job.org_id
    open_cases = db.scalar(select(func.count()).select_from(ExitCase).where(
        ExitCase.org_id == org, ExitCase.state.not_in(("closed", "withdrawn"))))
    overdue = db.scalar(select(func.count()).select_from(ExitTask).where(
        ExitTask.org_id == org, ExitTask.status == "open", ExitTask.due_date < date.today()))
    pending = db.scalar(select(func.count()).select_from(Approval).where(Approval.org_id == org,
                                                                        Approval.status == "pending"))
    bounced = db.scalar(select(func.count()).select_from(NoticeMessage).where(
        NoticeMessage.org_id == org, NoticeMessage.status == "bounced", NoticeMessage.is_test.is_(False)))
    title = (f"Weekly summary: {open_cases} open cases, {overdue} overdue tasks, {pending} pending approvals, "
             f"{bounced} bounced notices")
    notify_roles(db, org, ["hr"], "weekly_report", title, "/dashboard")
