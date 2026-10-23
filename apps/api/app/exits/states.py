"""Exit case state machine.

Main path (forward only):
identified → notice_drafted → notice_approved → notice_sent → notice_period → last_day_set → fnf_draft
→ fnf_approved → documents_issued → effective → closed

Side states: on_hold (returns to the state it was held from) and withdrawn (terminal).
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import audit
from app.deps import Ctx
from app.models import ExitCase

MAIN = ["identified", "notice_drafted", "notice_approved", "notice_sent", "notice_period", "last_day_set",
        "fnf_draft", "fnf_approved", "documents_issued", "effective", "closed"]
TERMINAL = {"closed", "withdrawn"}
LABELS = {
    "identified": "Identified", "notice_drafted": "Notice drafted", "notice_approved": "Notice approved",
    "notice_sent": "Notice sent", "notice_period": "Notice period", "last_day_set": "Last day set",
    "fnf_draft": "FNF draft", "fnf_approved": "FNF approved", "documents_issued": "Documents issued",
    "effective": "Effective", "closed": "Closed", "on_hold": "On hold", "withdrawn": "Withdrawn",
}


def index(state: str) -> int:
    return MAIN.index(state) if state in MAIN else -1


def reached(case: ExitCase, state: str) -> bool:
    s = case.held_from_state if case.state == "on_hold" else case.state
    return s in MAIN and index(s) >= index(state)


def require_active(case: ExitCase) -> None:
    if case.state == "on_hold":
        raise HTTPException(423, "The case is on hold")
    if case.state in TERMINAL:
        raise HTTPException(409, f"The case is {case.state}")


def advance(db: Session, ctx: Ctx, case: ExitCase, to: str) -> bool:
    """Move forward to `to` if that's ahead of the current state. Returns True if the state changed."""
    require_active(case)
    if index(to) <= index(case.state):
        return False
    before = case.state
    case.state = to
    audit.record(db, ctx, "exit_case", case.id, "state_change", {"state": before}, {"state": to})
    from app.exits.tasks import ensure_tasks  # tasks depend on states; import here to avoid a cycle

    ensure_tasks(db, case, to)
    return True


def hold(db: Session, ctx: Ctx, case: ExitCase, reason: str) -> None:
    if case.state == "on_hold":
        return
    if case.state in TERMINAL:
        raise HTTPException(409, f"The case is {case.state}")
    case.held_from_state, case.state, case.hold_reason = case.state, "on_hold", reason
    audit.record(db, ctx, "exit_case", case.id, "hold", {"state": case.held_from_state}, {"state": "on_hold"}, reason)


def release(db: Session, ctx: Ctx, case: ExitCase, note: str) -> None:
    if case.state != "on_hold":
        raise HTTPException(409, "The case isn't on hold")
    case.state, case.held_from_state = case.held_from_state, None
    audit.record(db, ctx, "exit_case", case.id, "release_hold", {"state": "on_hold"}, {"state": case.state}, note)
