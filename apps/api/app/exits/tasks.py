"""Tasks created automatically as an exit case moves through its stages."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClearanceItem, ExitCase, ExitTask

# stage -> [(auto_key, title, owner_role, due_in_days | "lwd")]
STAGE_TASKS: dict[str, list[tuple[str, str, str, int | str | None]]] = {
    "identified": [
        ("confirm_reason", "Confirm reason code and link evidence", "hr", 3),
        ("confirm_contacts", "Confirm work and personal email addresses", "hr", 3),
    ],
    "notice_sent": [
        ("handover_plan", "Agree a handover plan for open work", "manager", 7),
        ("request_access_revocation", "Request access revocation for the last working day", "hr", "lwd"),
        ("collect_assets", "Arrange return of company assets", "hr", "lwd"),
    ],
    "last_day_set": [
        ("payroll_inputs", "Confirm payroll inputs for FNF (bank details, leave, recoveries)", "finance", "lwd"),
        ("compute_fnf", "Compute the FNF statement", "hr", "lwd"),
    ],
    "fnf_approved": [
        ("pay_fnf", "Pay the approved FNF and record the payment", "finance", 2),
        ("issue_relieving", "Issue relieving and experience letters after clearance", "hr", 3),
    ],
    "effective": [("close_case", "Check all items are complete and close the case", "hr", 7)],
}

CLEARANCE = [
    ("access", "access_email", "Email account", "hr"),
    ("access", "access_vpn", "VPN", "hr"),
    ("access", "access_apps", "Internal applications", "hr"),
    ("access", "access_building", "Building access", "hr"),
    ("asset", "asset_laptop", "Laptop", "hr"),
    ("asset", "asset_phone", "Phone", "hr"),
    ("asset", "asset_card", "Access card", "hr"),
    ("asset", "asset_documents", "Company documents", "hr"),
    ("handover", "handover_note", "Handover note from manager", "manager"),
    ("signoff", "signoff_manager", "Manager sign-off", "manager"),
    ("signoff", "signoff_it", "IT sign-off", "hr"),
    ("signoff", "signoff_hr", "HR sign-off", "hr"),
]


def ensure_tasks(db: Session, case: ExitCase, stage: str) -> None:
    existing = set(db.scalars(select(ExitTask.auto_key).where(ExitTask.exit_case_id == case.id)))
    for key, title, role, due in STAGE_TASKS.get(stage, []):
        if key in existing:
            continue
        if due == "lwd":
            due_date = case.last_working_day
        elif isinstance(due, int):
            due_date = date.today() + timedelta(days=due)
        else:
            due_date = None
        db.add(ExitTask(org_id=case.org_id, exit_case_id=case.id, auto_key=key, stage=stage, title=title,
                        owner_role=role, due_date=due_date))
    if stage == "notice_sent":
        have = set(db.scalars(select(ClearanceItem.key).where(ClearanceItem.exit_case_id == case.id)))
        for cat, key, label, role in CLEARANCE:
            if key not in have:
                db.add(ClearanceItem(org_id=case.org_id, exit_case_id=case.id, category=cat, key=key, label=label,
                                     owner_role=role))
    db.flush()


def add_task(db: Session, case: ExitCase, key: str, title: str, role: str, due: date | None = None) -> ExitTask:
    t = db.scalar(select(ExitTask).where(ExitTask.exit_case_id == case.id, ExitTask.auto_key == key))
    if t is None:
        t = ExitTask(org_id=case.org_id, exit_case_id=case.id, auto_key=key, stage=case.state, title=title,
                     owner_role=role, due_date=due)
        db.add(t)
        db.flush()
    elif t.status != "open":
        t.status = "open"
    return t


def cancel_open(db: Session, case: ExitCase) -> None:
    for t in db.scalars(select(ExitTask).where(ExitTask.exit_case_id == case.id, ExitTask.status == "open")):
        t.status = "cancelled"
