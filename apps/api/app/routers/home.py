"""Dashboard summary and in-app notifications."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import people
from app.compliance.rules import rulebook
from app.config import RULESET_MODE
from app.db import get_db
from app.deps import Ctx, get_ctx
from app.exits.service import visible_cases
from app.exits.states import LABELS
from app.models import Employee, ExitCase, ExitTask, Grievance, NoticeMessage, Notification, Pip, Plan, utcnow
from app.serialize import to_dict
from app.workflow import approvals
from app.workflow.approvals import LINKS, TITLES

router = APIRouter(tags=["home"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/dashboard")
def dashboard(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    today = date.today()
    cases = list(db.scalars(visible_cases(ctx)))
    case_ids = [c.id for c in cases]
    my_roles = {ctx.role} | ({"hr", "finance", "manager", "legal"} if ctx.role == "admin" else set())
    tasks = []
    for t in db.scalars(select(ExitTask).where(ExitTask.exit_case_id.in_(case_ids or [0]), ExitTask.status == "open",
                                               ExitTask.owner_role.in_(my_roles))
                        .order_by(ExitTask.due_date)):
        if t.due_date is None or t.due_date <= today + timedelta(days=7):
            e = db.get(Employee, db.get(ExitCase, t.exit_case_id).employee_id)
            tasks.append(to_dict(t, employee_code=e.employee_code, overdue=bool(t.due_date and t.due_date < today)))
    alerts = []
    book = rulebook(db, ctx.org_id)
    if book.unverified:
        alerts.append({"kind": "rules", "severity": "block" if RULESET_MODE == "production" else "warning",
                       "text": f"{len(book.unverified)} jurisdiction rules are unverified: not for use with real employees",
                       "link": "/rules"})
    bounced = db.scalar(select(func.count()).select_from(NoticeMessage).where(
        NoticeMessage.org_id == ctx.org_id, NoticeMessage.status == "bounced", NoticeMessage.is_test.is_(False)))
    if bounced and ctx.has("hr"):
        alerts.append({"kind": "bounce", "severity": "warning", "text": f"{bounced} notices bounced", "link": "/notices"})
    visible_ids = {e.id for e in db.scalars(people.visible_query(ctx))}
    overdue_pips = sum(1 for p in db.scalars(select(Pip).where(Pip.org_id == ctx.org_id, Pip.status == "active",
                                                               Pip.end_date < today)) if p.employee_id in visible_ids)
    if overdue_pips and ctx.has("hr", "manager", "legal"):
        alerts.append({"kind": "pip", "severity": "warning", "text": f"{overdue_pips} PIPs are past their end date",
                       "link": "/performance"})
    late_acks = db.scalar(select(func.count()).select_from(Grievance).where(
        Grievance.org_id == ctx.org_id, Grievance.acknowledged_at.is_(None), Grievance.ack_due_on < today))
    if late_acks and ctx.has("hr", "legal"):
        alerts.append({"kind": "grievance", "severity": "warning",
                       "text": f"{late_acks} grievances are past their acknowledgement date", "link": "/grievances"})
    states: dict[str, int] = {}
    for c in cases:
        states[c.state] = states.get(c.state, 0) + 1
    plans = db.scalars(select(Plan).where(Plan.org_id == ctx.org_id).order_by(Plan.id.desc())).all() \
        if ctx.role != "manager" else []
    return {
        "tasks": tasks,
        "approvals": [to_dict(a, title=TITLES[a.entity_type], link=LINKS[a.entity_type].format(id=a.entity_id))
                      for a in approvals.pending_for(db, ctx)],
        "cases": {"open": sum(1 for c in cases if c.state not in ("closed", "withdrawn")),
                  "by_state": [{"state": s, "label": LABELS.get(s, s), "count": n} for s, n in states.items()]},
        "plans": [{"id": p.id, "name": p.name, "status": p.status, "version": p.version,
                   "created_by": p.created_by, "created_at": p.created_at, "last_run_at": p.last_run_at,
                   "target_count": p.target_count, "selection_method": p.selection_method,
                   "filters": p.filters} for p in plans],
        "alerts": alerts,
        "people": {"total": len(visible_ids)},
    }


@router.get("/notifications")
def notifications(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == ctx.user_id)
                      .order_by(Notification.read_at.is_not(None), Notification.id.desc()).limit(50)).all()
    return {"unread": sum(1 for n in rows if n.read_at is None), "items": [to_dict(n) for n in rows]}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == ctx.user_id))
    if n and n.read_at is None:
        n.read_at = utcnow()
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == ctx.user_id, Notification.read_at.is_(None))):
        n.read_at = utcnow()
    db.commit()
