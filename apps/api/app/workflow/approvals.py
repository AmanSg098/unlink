"""Generic approval engine for plans, notice batches, FNF, exit effectiveness, HRIS pushes and more.

An approval round is started with the content hash of the item. Each step is decided by someone holding
one of the step's roles. Rules enforced here:
- the person who prepared the item can't approve any step;
- one person can't approve two steps of the same round;
- the item's current content hash must equal the hash the round started with (edits invalidate approval);
- rejection needs a comment and supersedes the rest of the round.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.deps import Ctx
from app.models import Approval, utcnow
from app.notify import notify_roles
from app.workflow.sequences import SEQUENCES

LINKS = {
    "plan": "/plans/{id}",
    "notice_batch": "/notices?batch={id}",
    "fnf": "/fnf?statement={id}",
    "exit_effective": "/cases/{id}",
    "hris_push": "/cases/{id}",
    "reason_other": "/cases/{id}",
    "clearance_exception": "/cases/{id}",
    "template": "/notices/templates/{id}",
}
TITLES = {
    "plan": "A reduction plan is waiting for your review",
    "notice_batch": "A notice batch is waiting for your approval",
    "fnf": "An FNF statement is waiting for your review",
    "exit_effective": "An exit is waiting to be approved as effective",
    "hris_push": "An HRIS update is waiting for approval",
    "reason_other": "An exit reason needs legal approval",
    "clearance_exception": "A clearance exception needs approval",
    "template": "A notice template is waiting for legal approval",
}


def _latest_round(db: Session, org_id: int, entity_type: str, entity_id: int) -> list[Approval]:
    rnd = db.scalar(select(func.max(Approval.round)).where(
        Approval.org_id == org_id, Approval.entity_type == entity_type, Approval.entity_id == entity_id))
    if rnd is None:
        return []
    return list(db.scalars(select(Approval).where(
        Approval.org_id == org_id, Approval.entity_type == entity_type, Approval.entity_id == entity_id,
        Approval.round == rnd).order_by(Approval.step_index)))


def history(db: Session, org_id: int, entity_type: str, entity_id: int) -> list[Approval]:
    return list(db.scalars(select(Approval).where(
        Approval.org_id == org_id, Approval.entity_type == entity_type, Approval.entity_id == entity_id)
        .order_by(Approval.round, Approval.step_index)))


def _notify_next(db: Session, ctx: Ctx, entity_type: str, entity_id: int, steps: list[Approval]) -> None:
    nxt = next((s for s in steps if s.status == "pending"), None)
    if nxt:
        notify_roles(db, ctx.org_id, list(nxt.roles), "approval", TITLES[entity_type],
                     LINKS[entity_type].format(id=entity_id), exclude=(ctx.user,))


def start(db: Session, ctx: Ctx, entity_type: str, entity_id: int, content_hash: str,
          conditions: dict[str, bool] | None = None, sequence: str | None = None) -> list[Approval]:
    sequence = sequence or entity_type
    conditions = conditions or {}
    prev = _latest_round(db, ctx.org_id, entity_type, entity_id)
    for s in prev:
        if s.status == "pending":
            s.status = "superseded"
    rnd = (prev[0].round + 1) if prev else 1
    steps = []
    for i, st in enumerate(SEQUENCES[sequence]):
        skipped = st.condition is not None and not conditions.get(st.condition)
        steps.append(Approval(org_id=ctx.org_id, entity_type=entity_type, entity_id=entity_id, sequence=sequence,
                              round=rnd, step_index=i, step=st.name, roles=list(st.roles),
                              status="skipped" if skipped else "pending", prepared_by=ctx.user,
                              content_hash=content_hash))
    db.add_all(steps)
    db.flush()
    audit.record(db, ctx, entity_type, entity_id, "approval_requested", None,
                 {"round": rnd, "steps": [s.step for s in steps if s.status == "pending"], "content_hash": content_hash})
    _notify_next(db, ctx, entity_type, entity_id, steps)
    return steps


def current_step(db: Session, org_id: int, entity_type: str, entity_id: int) -> Approval | None:
    return next((s for s in _latest_round(db, org_id, entity_type, entity_id) if s.status == "pending"), None)


def decide(db: Session, ctx: Ctx, entity_type: str, entity_id: int, approve: bool, comment: str | None,
           current_hash: str, forbidden: dict[str, str] | None = None) -> tuple[Approval, bool]:
    """Decide the current step. Returns (step, finished) where finished means fully approved."""
    steps = _latest_round(db, ctx.org_id, entity_type, entity_id)
    step = next((s for s in steps if s.status == "pending"), None)
    if step is None:
        raise HTTPException(409, "Nothing is waiting for approval")
    if not ctx.has(*step.roles):
        raise HTTPException(403, f"This step needs: {' or '.join(('admin', *step.roles))}")
    if ctx.user == step.prepared_by:
        raise HTTPException(403, "Whoever prepared an item can't approve it")
    if any(s.decided_by == ctx.user and s.status == "approved" for s in steps):
        raise HTTPException(403, "You've already approved another step of this item; a different person must decide")
    for who, why in (forbidden or {}).items():
        if ctx.user == who:
            raise HTTPException(403, why)
    if current_hash != step.content_hash:
        raise HTTPException(409, "The item changed after it was submitted; it must be resubmitted")
    if not approve and not (comment and comment.strip()):
        raise HTTPException(422, "A comment is required to reject")

    step.decided_by, step.decided_at, step.comment = ctx.user, utcnow(), comment
    if approve:
        step.status = "approved"
    else:
        step.status = "rejected"
        for s in steps:
            if s.status == "pending":
                s.status = "superseded"
    finished = approve and all(s.status in ("approved", "skipped") for s in steps)
    audit.record(db, ctx, entity_type, entity_id, f"approval_{'approved' if approve else 'rejected'}",
                 {"step": step.step}, {"step": step.step, "round": step.round, "finished": finished,
                                       "content_hash": step.content_hash}, comment)
    if approve and not finished:
        _notify_next(db, ctx, entity_type, entity_id, steps)
    return step, finished


def is_approved(db: Session, org_id: int, entity_type: str, entity_id: int, current_hash: str) -> bool:
    steps = _latest_round(db, org_id, entity_type, entity_id)
    return bool(steps) and all(s.status in ("approved", "skipped") for s in steps) \
        and all(s.content_hash == current_hash for s in steps)


def pending_for(db: Session, ctx: Ctx) -> list[Approval]:
    """Pending steps the caller could decide now."""
    rows = db.scalars(select(Approval).where(Approval.org_id == ctx.org_id, Approval.status == "pending")
                      .order_by(Approval.created_at)).all()
    out = []
    for a in rows:
        # Only the first pending step of each round is actionable.
        first = current_step(db, ctx.org_id, a.entity_type, a.entity_id)
        if first and first.id == a.id and ctx.has(*a.roles) and a.prepared_by != ctx.user:
            out.append(a)
    return out
