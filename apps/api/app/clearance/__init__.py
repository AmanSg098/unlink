"""Access and asset clearance checklist per exit case."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.crypto import content_hash
from app.deps import Ctx
from app.exits import states
from app.integrations import enabled_integration
from app.models import ClearanceItem, ExitCase, utcnow
from app.queue import enqueue
from app.workflow import approvals

STATUSES = {
    "access": ["pending", "requested", "revoked", "verified", "waived"],
    "asset": ["pending", "returned", "missing", "waived"],
    "handover": ["pending", "done", "waived"],
    "signoff": ["pending", "done"],
}
COMPLETE = {"verified", "returned", "done", "waived"}


def items(db: Session, case: ExitCase) -> list[ClearanceItem]:
    return list(db.scalars(select(ClearanceItem).where(ClearanceItem.exit_case_id == case.id).order_by(ClearanceItem.id)))


def update(db: Session, ctx: Ctx, case: ExitCase, item_id: int, status: str, note: str | None) -> ClearanceItem:
    states.require_active(case)
    it = db.scalar(select(ClearanceItem).where(ClearanceItem.id == item_id, ClearanceItem.exit_case_id == case.id))
    if it is None:
        raise HTTPException(404, "Clearance item not found")
    if status not in STATUSES[it.category]:
        raise HTTPException(422, f"Status must be one of {', '.join(STATUSES[it.category])}")
    allowed = ctx.has("hr") or (it.owner_role == "manager" and ctx.role == "manager")
    if not allowed:
        raise HTTPException(403, "Only HR or the employee's manager can update this item")
    if status == "waived" and not (note and note.strip()):
        raise HTTPException(422, "Waiving an item needs a note")
    before = {"status": it.status}
    it.status, it.note, it.updated_by, it.updated_at = status, note, ctx.user, utcnow()
    audit.record(db, ctx, "clearance", it.id, "update", before,
                 {"status": status, "key": it.key, "exit_case_id": case.id}, note)
    if it.category == "access" and status == "requested":
        ticket = enabled_integration(db, ctx.org_id, "ticketing")
        if ticket:
            enqueue(db, ctx.org_id, "ticket_create", {"clearance_item_id": it.id})
    return it


def complete(db: Session, case: ExitCase) -> bool:
    its = items(db, case)
    return bool(its) and all(i.status in COMPLETE for i in its)


def exception_hash(case: ExitCase, db: Session) -> str:
    return content_hash({"case": case.id, "open": sorted(i.key for i in items(db, case) if i.status not in COMPLETE)})


def exception_approved(db: Session, case: ExitCase) -> bool:
    return approvals.is_approved(db, case.org_id, "clearance_exception", case.id, exception_hash(case, db))
