"""Hard exclusions: people who can never be selected or exited by a plan.

They are applied before scoring and can't be bypassed by weights, filters, or manual overrides,
under any role (including admin).
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Employee, Grievance, Pip

DEFAULT_PROTECTED_LEAVE = frozenset({"maternity", "medical"})


@dataclass(frozen=True)
class ExclusionContext:
    active_pip: frozenset[int] = frozenset()
    open_grievance: frozenset[int] = frozenset()
    protected_leave: frozenset[str] = DEFAULT_PROTECTED_LEAVE
    extra: dict[int, str] = field(default_factory=dict)  # employee_id -> reason from ruleset checks


def build_context(db: Session, org_id: int, as_of: date, protected_leave: frozenset[str] | None = None
                  ) -> ExclusionContext:
    active_pip = frozenset(db.scalars(select(Pip.employee_id).where(
        Pip.org_id == org_id, Pip.status == "active", Pip.end_date >= as_of)))
    open_grievance = frozenset(db.scalars(select(Grievance.employee_id).where(
        Grievance.org_id == org_id, Grievance.status.in_(("open", "under_review", "appealed")))))
    return ExclusionContext(active_pip=active_pip, open_grievance=open_grievance,
                            protected_leave=protected_leave or DEFAULT_PROTECTED_LEAVE)


def hard_exclusion_reason(e: Employee, xc: ExclusionContext | None = None) -> str | None:
    xc = xc or ExclusionContext()
    if e.leave_status in xc.protected_leave:
        return f"On {e.leave_status} leave"
    if e.protected_flag:
        return "Protected status"
    if e.legal_hold:
        return "Legal hold"
    if e.id in xc.open_grievance:
        return "Open grievance"
    if e.id in xc.active_pip:
        return "Active PIP within its end date"
    if e.status == "on_notice":
        return "Notice period already started"
    if e.status == "exited":
        return "Already exited"
    return xc.extra.get(e.id)
