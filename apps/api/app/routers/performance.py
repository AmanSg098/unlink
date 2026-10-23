from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, people
from app.crypto import encrypt_str
from app.db import get_db
from app.deps import Ctx, require
from app.models import (
    Checkin,
    CheckinAction,
    Employee,
    Feedback,
    Goal,
    GoalProgress,
    Pip,
    PipMilestone,
    Review,
    ReviewCycle,
    utcnow,
)
from app.performance import calibration, close_pip, default_end, employee_for, finalize_cycle, missing_evidence, store_evidence
from app.schemas import (
    AckIn,
    CalibrateIn,
    CheckinIn,
    CycleIn,
    FeedbackIn,
    GoalIn,
    MilestoneIn,
    PipCloseIn,
    PipIn,
    ProgressIn,
    ReviewIn,
)
from app.serialize import to_dict

router = APIRouter(prefix="/performance", tags=["performance"])
VIEW = require("hr", "legal", "manager")
HR = require("hr")
HR_LEGAL = require("hr", "legal")
WRITE = require("hr", "manager")


def _cycle(db: Session, ctx: Ctx, cid: int) -> ReviewCycle:
    c = db.scalar(select(ReviewCycle).where(ReviewCycle.id == cid, ReviewCycle.org_id == ctx.org_id))
    if c is None:
        raise HTTPException(404, "Review cycle not found")
    return c


def _pip(db: Session, ctx: Ctx, pid: int) -> Pip:
    p = db.scalar(select(Pip).where(Pip.id == pid, Pip.org_id == ctx.org_id))
    if p is None:
        raise HTTPException(404, "PIP not found")
    people.get_visible(db, ctx, p.employee_id)  # managers: own team only
    return p


def _emp_brief(e: Employee) -> dict:
    return {"employee_id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
            "department": e.department, "role": e.role}


# ------------------------------------------------------------------ overview
@router.get("/overview")
def overview(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    visible = {e.id: e for e in db.scalars(people.visible_query(ctx))}
    pips = [p for p in db.scalars(select(Pip).where(Pip.org_id == ctx.org_id)) if p.employee_id in visible]
    soon = date.today() + timedelta(days=14)
    return {
        "pips": {"proposed": sum(p.status == "proposed" for p in pips), "active": sum(p.status == "active" for p in pips),
                 "ending_soon": sum(p.status == "active" and p.end_date <= soon for p in pips),
                 "overdue": sum(p.status == "active" and p.end_date < date.today() for p in pips),
                 "closed_not_met": sum(p.outcome == "not_met" for p in pips)},
        "pipeline": [{**to_dict(p), **_emp_brief(visible[p.employee_id])}
                     for p in sorted(pips, key=lambda p: (p.status != "active", p.end_date)) if p.status != "closed"
                     or (date.today() - p.end_date).days < 90],
        "cycles": [to_dict(c) for c in db.scalars(select(ReviewCycle).where(ReviewCycle.org_id == ctx.org_id)
                                                  .order_by(ReviewCycle.period_end.desc()))],
        "missing_evidence": len(missing_evidence(db, ctx)) if ctx.has("hr", "legal") else None,
        "rating_distribution": {str(k): sum(1 for e in visible.values() if round(e.performance_rating) == k)
                                for k in range(1, 6)},
    }


# ------------------------------------------------------------------ cycles and reviews
@router.post("/cycles", status_code=201)
def create_cycle(body: CycleIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    if body.period_end <= body.period_start:
        raise HTTPException(422, "The period must end after it starts")
    c = ReviewCycle(org_id=ctx.org_id, created_by=ctx.user, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, ctx, "review_cycle", c.id, "create", None, body.model_dump(mode="json"))
    db.commit()
    return to_dict(c)


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    c = _cycle(db, ctx, cycle_id)
    visible = {e.id: e for e in db.scalars(people.visible_query(ctx))}
    reviews = {r.employee_id: r for r in db.scalars(select(Review).where(Review.cycle_id == c.id))}
    rows = [{**_emp_brief(e), "review": to_dict(reviews[e.id]) if e.id in reviews else None}
            for e in sorted(visible.values(), key=lambda e: e.employee_code) if e.status != "exited"]
    return {"cycle": to_dict(c), "rows": rows,
            "calibration": calibration(db, ctx, c) if ctx.has("hr", "legal") else None}


@router.put("/cycles/{cycle_id}/reviews")
def upsert_review(cycle_id: int, body: ReviewIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    c = _cycle(db, ctx, cycle_id)
    if c.status == "closed":
        raise HTTPException(409, "This cycle is closed")
    for v in (body.self_rating, body.manager_rating):
        if v is not None and v > c.scale_max:
            raise HTTPException(422, f"Ratings use a 1-{c.scale_max} scale")
    e = employee_for(db, ctx, body.employee_id)
    r = db.scalar(select(Review).where(Review.cycle_id == c.id, Review.employee_id == e.id))
    if r is None:
        r = Review(org_id=ctx.org_id, cycle_id=c.id, employee_id=e.id)
        db.add(r)
    data = body.model_dump(exclude_unset=True, exclude={"employee_id"})
    before = {k: getattr(r, k) for k in data}
    for k, v in data.items():
        setattr(r, k, v)
    r.updated_by = ctx.user
    db.flush()
    audit.record(db, ctx, "review", r.id, "update", before, {**data, "cycle_id": c.id, "employee_id": e.id})
    db.commit()
    return to_dict(r)


@router.post("/reviews/{review_id}/calibrate")
def calibrate(review_id: int, body: CalibrateIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    r = db.scalar(select(Review).where(Review.id == review_id, Review.org_id == ctx.org_id))
    if r is None:
        raise HTTPException(404, "Review not found")
    c = db.get(ReviewCycle, r.cycle_id)
    if c.status == "closed":
        raise HTTPException(409, "This cycle is closed")
    if body.calibrated_rating > c.scale_max:
        raise HTTPException(422, f"Ratings use a 1-{c.scale_max} scale")
    before = {"calibrated_rating": r.calibrated_rating}
    r.calibrated_rating, r.calibrated_by, r.calibrated_at = body.calibrated_rating, ctx.user, utcnow()
    if c.status == "open":
        c.status = "calibrating"
    audit.record(db, ctx, "review", r.id, "calibrate", before, {"calibrated_rating": r.calibrated_rating,
                                                                "employee_id": r.employee_id})
    db.commit()
    return to_dict(r)


@router.post("/cycles/{cycle_id}/close")
def close_cycle(cycle_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    c = _cycle(db, ctx, cycle_id)
    n = finalize_cycle(db, ctx, c)
    db.commit()
    return {"cycle": to_dict(c), "ratings_updated": n}


# ------------------------------------------------------------------ goals, check-ins, feedback
@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    e = employee_for(db, ctx, body.employee_id)
    g = Goal(org_id=ctx.org_id, created_by=ctx.user, **body.model_dump())
    db.add(g)
    db.flush()
    audit.record(db, ctx, "goal", g.id, "create", None, {"employee_id": e.id, "title": g.title})
    db.commit()
    return to_dict(g)


@router.post("/goals/{goal_id}/progress")
def goal_progress(goal_id: int, body: ProgressIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    g = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.org_id == ctx.org_id))
    if g is None:
        raise HTTPException(404, "Goal not found")
    employee_for(db, ctx, g.employee_id)
    db.add(GoalProgress(org_id=ctx.org_id, goal_id=g.id, pct=body.pct, note=body.note, recorded_by=ctx.user))
    before = g.progress_pct
    g.progress_pct = body.pct
    g.status = "done" if body.pct >= 100 else "open"
    audit.record(db, ctx, "goal", g.id, "progress", {"pct": before}, {"pct": body.pct})
    db.commit()
    return to_dict(g)


@router.post("/checkins", status_code=201)
def create_checkin(body: CheckinIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    e = employee_for(db, ctx, body.employee_id)
    c = Checkin(org_id=ctx.org_id, employee_id=e.id, scheduled_for=body.scheduled_for, held_on=body.held_on,
                summary=body.summary, sentiment=body.sentiment,
                private_note_enc=encrypt_str(body.private_note) if body.private_note else None, created_by=ctx.user)
    db.add(c)
    db.flush()
    for a in body.actions:
        db.add(CheckinAction(org_id=ctx.org_id, checkin_id=c.id, **a.model_dump()))
    audit.record(db, ctx, "checkin", c.id, "create", None,
                 {"employee_id": e.id, "sentiment": c.sentiment, "actions": len(body.actions),
                  "private_note": bool(body.private_note)})
    db.commit()
    return to_dict(c, has_private_note=bool(c.private_note_enc))


@router.post("/checkin-actions/{action_id}/toggle")
def toggle_action(action_id: int, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    a = db.scalar(select(CheckinAction).where(CheckinAction.id == action_id, CheckinAction.org_id == ctx.org_id))
    if a is None:
        raise HTTPException(404, "Action not found")
    employee_for(db, ctx, db.get(Checkin, a.checkin_id).employee_id)
    a.done = not a.done
    db.commit()
    return to_dict(a)


@router.post("/feedback", status_code=201)
def create_feedback(body: FeedbackIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    e = employee_for(db, ctx, body.employee_id)
    f = Feedback(org_id=ctx.org_id, author=ctx.user, **body.model_dump())
    db.add(f)
    db.flush()
    audit.record(db, ctx, "feedback", f.id, "create", None, {"employee_id": e.id})
    db.commit()
    return to_dict(f)


# ------------------------------------------------------------------ PIPs
@router.get("/pips")
def list_pips(status: str | None = None, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    visible = {e.id: e for e in db.scalars(people.visible_query(ctx))}
    q = select(Pip).where(Pip.org_id == ctx.org_id)
    if status:
        q = q.where(Pip.status == status)
    return [{**to_dict(p), **_emp_brief(visible[p.employee_id])}
            for p in db.scalars(q.order_by(Pip.end_date)) if p.employee_id in visible]


@router.post("/pips", status_code=201)
def create_pip(body: PipIn, ctx: Ctx = Depends(require("hr", "legal", "manager")), db: Session = Depends(get_db)):
    e = employee_for(db, ctx, body.employee_id)
    if db.scalar(select(Pip.id).where(Pip.employee_id == e.id, Pip.status.in_(("proposed", "active")))):
        raise HTTPException(409, "This person already has an open PIP")
    end = body.end_date or default_end(body.start_date)
    if end <= body.start_date:
        raise HTTPException(422, "The end date must be after the start date")
    starts_active = ctx.has("hr", "legal")  # managers propose; HR or Legal start
    p = Pip(org_id=ctx.org_id, employee_id=e.id, reason_category=body.reason_category, gaps=body.gaps,
            success_criteria=body.success_criteria, support=body.support, start_date=body.start_date, end_date=end,
            checkin_dates=[d.isoformat() for d in body.checkin_dates], proposed_by=ctx.user,
            status="active" if starts_active else "proposed", activated_by=ctx.user if starts_active else None)
    db.add(p)
    db.flush()
    audit.record(db, ctx, "pip", p.id, "create", None, {"employee_id": e.id, "status": p.status, "end_date": end})
    db.commit()
    return to_dict(p)


@router.post("/pips/{pip_id}/activate")
def activate_pip(pip_id: int, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    p = _pip(db, ctx, pip_id)
    if p.status != "proposed":
        raise HTTPException(409, f"PIP is {p.status}")
    p.status, p.activated_by = "active", ctx.user
    audit.record(db, ctx, "pip", p.id, "activate", {"status": "proposed"}, {"status": "active"})
    db.commit()
    return to_dict(p)


@router.post("/pips/{pip_id}/milestones", status_code=201)
def add_milestone(pip_id: int, body: MilestoneIn, ctx: Ctx = Depends(WRITE), db: Session = Depends(get_db)):
    p = _pip(db, ctx, pip_id)
    if p.status != "active":
        raise HTTPException(409, "Milestones can only be recorded on an active PIP")
    m = PipMilestone(org_id=ctx.org_id, pip_id=p.id, manager_signed_by=ctx.user, **body.model_dump())
    db.add(m)
    db.flush()
    audit.record(db, ctx, "pip", p.id, "milestone", None, {"milestone_id": m.id, "on_date": m.on_date,
                                                          "outcome": m.outcome})
    db.commit()
    return to_dict(m)


@router.post("/pips/{pip_id}/ack")
def pip_ack(pip_id: int, body: AckIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    """Record the employee's acknowledgement of the PIP, or that they declined to sign (dated)."""
    p = _pip(db, ctx, pip_id)
    p.employee_ack, p.employee_ack_at = body.status, utcnow()
    audit.record(db, ctx, "pip", p.id, "employee_ack", None, {"status": body.status})
    db.commit()
    return to_dict(p)


@router.post("/milestones/{milestone_id}/ack")
def milestone_ack(milestone_id: int, body: AckIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    m = db.scalar(select(PipMilestone).where(PipMilestone.id == milestone_id, PipMilestone.org_id == ctx.org_id))
    if m is None:
        raise HTTPException(404, "Milestone not found")
    m.employee_ack, m.employee_ack_at = body.status, utcnow()
    audit.record(db, ctx, "pip", m.pip_id, "milestone_ack", None, {"milestone_id": m.id, "status": body.status})
    db.commit()
    return to_dict(m)


@router.post("/pips/{pip_id}/close")
def close(pip_id: int, body: PipCloseIn, ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    p = _pip(db, ctx, pip_id)
    close_pip(db, ctx, p, body.outcome, body.final_review, body.final_review_on)
    db.commit()
    return to_dict(p)


# ------------------------------------------------------------------ evidence and reports
ENTITY_EMPLOYEE = {"review": Review, "pip": Pip, "checkin": Checkin, "feedback": Feedback}


@router.post("/evidence", status_code=201)
async def upload_evidence(entity_type: str = Form(...), entity_id: int = Form(...), evidence_type: str = Form(...),
                          file: UploadFile = File(...), ctx: Ctx = Depends(require("hr", "legal", "manager")),
                          db: Session = Depends(get_db)):
    if entity_type == "pip_milestone":
        m = db.scalar(select(PipMilestone).where(PipMilestone.id == entity_id, PipMilestone.org_id == ctx.org_id))
        owner = db.get(Pip, m.pip_id).employee_id if m else None
    elif entity_type in ENTITY_EMPLOYEE:
        model = ENTITY_EMPLOYEE[entity_type]
        row = db.scalar(select(model).where(model.id == entity_id, model.org_id == ctx.org_id))
        owner = row.employee_id if row else None
    else:
        raise HTTPException(422, "Upload case evidence from the exit case")
    if owner is None:
        raise HTTPException(404, f"{entity_type} not found")
    employee_for(db, ctx, owner)
    ev = store_evidence(db, ctx, employee_id=owner, entity_type=entity_type, entity_id=entity_id,
                        evidence_type=evidence_type, filename=file.filename or "file", data=await file.read())
    db.commit()
    return to_dict(ev)


@router.get("/missing-evidence")
def report_missing(ctx: Ctx = Depends(HR_LEGAL), db: Session = Depends(get_db)):
    return missing_evidence(db, ctx)
