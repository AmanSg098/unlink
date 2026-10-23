"""Grievances and appeals. A grievance about the process, reason or selection puts the case on hold.

Messages to the employee (acknowledgement, outcome) go through the normal notice flow: a draft and a
one-message batch that a person approves and releases.
"""

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.crypto import decrypt_str, encrypt_str
from app.deps import Ctx
from app.exits import states
from app.models import Appeal, ExitCase, Grievance, Plan, utcnow
from app.notices import create_batch, create_draft, current_template
from app.notify import notify_roles

HOLD_CATEGORIES = {"process", "reason", "selection"}
CATEGORIES = ("process", "reason", "selection", "fnf", "other")
OUTCOMES = {"upheld": "Upheld", "partly_upheld": "Partly upheld", "rejected": "Not upheld"}


def get(db: Session, ctx: Ctx, gid: int) -> Grievance:
    g = db.scalar(select(Grievance).where(Grievance.id == gid, Grievance.org_id == ctx.org_id))
    if g is None:
        raise HTTPException(404, "Grievance not found")
    return g


def ref(g: Grievance) -> str:
    return f"GRV-{g.id:05d}"


def _prepare_message(db: Session, ctx: Ctx, case: ExitCase, key: str, extra: dict, label: str) -> None:
    t = current_template(db, ctx.org_id, key)
    if t is None:
        return
    d = create_draft(db, ctx, case, t, extra)
    create_batch(db, ctx, f"{label} · case {case.id}", [d.id])
    notify_roles(db, ctx.org_id, ["hr"], "grievance", f"{label}: a message is ready for review", "/notices")


def log(db: Session, ctx: Ctx, case: ExitCase, category: str, description: str) -> Grievance:
    if category not in CATEGORIES:
        raise HTTPException(422, f"Category must be one of {', '.join(CATEGORIES)}")
    if not description.strip():
        raise HTTPException(422, "Please describe the concern")
    plan = db.get(Plan, case.plan_id)
    days = int((rulebook(db, ctx.org_id, plan.ruleset_id).value("IN-GRIEV-001") or {}).get("days", 3))
    g = Grievance(org_id=ctx.org_id, exit_case_id=case.id, employee_id=case.employee_id, category=category,
                  description_enc=encrypt_str(description), logged_by=ctx.user,
                  ack_due_on=date.today() + timedelta(days=days))
    db.add(g)
    db.flush()
    audit.record(db, ctx, "grievance", g.id, "log", None, {"exit_case_id": case.id, "category": category})
    if category in HOLD_CATEGORIES and case.state not in ("on_hold", "withdrawn", "closed", "effective"):
        states.hold(db, ctx, case, f"Grievance {ref(g)} ({category})")
    _prepare_message(db, ctx, case, "grievance_acknowledgement",
                     {"grievance_ref": ref(g), "grievance_date": date.today().isoformat()}, "Grievance acknowledgement")
    notify_roles(db, ctx.org_id, ["hr", "legal"], "grievance", "A new grievance was logged", f"/grievances?id={g.id}")
    return g


def acknowledge(db: Session, ctx: Ctx, g: Grievance) -> None:
    g.acknowledged_at = utcnow()
    if g.status == "open":
        g.status = "under_review"
    audit.record(db, ctx, "grievance", g.id, "acknowledge", None, {"exit_case_id": g.exit_case_id})


def decide(db: Session, ctx: Ctx, g: Grievance, findings: str, outcome: str, reasons: str) -> None:
    if g.status not in ("open", "under_review"):
        raise HTTPException(409, f"Grievance is {g.status}")
    if outcome not in OUTCOMES or not reasons.strip() or not findings.strip():
        raise HTTPException(422, "Findings, an outcome and reasons are required")
    case = db.get(ExitCase, g.exit_case_id)
    if case and ctx.user in (case.owner, case.created_by):
        raise HTTPException(403, "Someone involved in the original decision can't decide the grievance")
    g.findings, g.outcome, g.outcome_reasons = findings, outcome, reasons
    g.decided_by, g.decided_at, g.status = ctx.user, utcnow(), "decided"
    audit.record(db, ctx, "grievance", g.id, "decide", None, {"outcome": outcome, "exit_case_id": g.exit_case_id}, reasons)
    if case:
        _prepare_message(db, ctx, case, "appeal_outcome",
                         {"grievance_ref": ref(g), "outcome_text": OUTCOMES[outcome], "outcome_reasons": reasons,
                          "can_appeal": True}, "Grievance outcome")


def appeal(db: Session, ctx: Ctx, g: Grievance, grounds: str) -> Appeal:
    if g.status != "decided":
        raise HTTPException(409, "Only a decided grievance can be appealed")
    if db.scalar(select(Appeal.id).where(Appeal.grievance_id == g.id)):
        raise HTTPException(409, "This grievance has already been appealed")
    a = Appeal(org_id=ctx.org_id, grievance_id=g.id, grounds_enc=encrypt_str(grounds))
    db.add(a)
    g.status = "appealed"
    db.flush()
    audit.record(db, ctx, "grievance", g.id, "appeal", None, {"appeal_id": a.id, "exit_case_id": g.exit_case_id})
    notify_roles(db, ctx.org_id, ["hr", "legal"], "grievance", "A grievance outcome was appealed", f"/grievances?id={g.id}")
    return a


def decide_appeal(db: Session, ctx: Ctx, g: Grievance, outcome: str, reasons: str) -> None:
    a = db.scalar(select(Appeal).where(Appeal.grievance_id == g.id))
    if a is None or a.status != "open":
        raise HTTPException(409, "There's no open appeal")
    case = db.get(ExitCase, g.exit_case_id)
    if ctx.user == g.decided_by or (case and ctx.user in (case.owner, case.created_by)):
        raise HTTPException(403, "An appeal must be decided by someone who didn't take the original decision")
    if outcome not in OUTCOMES or not reasons.strip():
        raise HTTPException(422, "An outcome and reasons are required")
    a.outcome, a.reasons, a.decided_by, a.decided_at, a.status = outcome, reasons, ctx.user, utcnow(), "decided"
    g.status = "closed"
    audit.record(db, ctx, "grievance", g.id, "decide_appeal", None,
                 {"outcome": outcome, "exit_case_id": g.exit_case_id}, reasons)
    if case:
        _prepare_message(db, ctx, case, "appeal_outcome",
                         {"grievance_ref": ref(g), "outcome_text": f"Appeal {OUTCOMES[outcome].lower()}",
                          "outcome_reasons": reasons, "can_appeal": False}, "Appeal outcome")


def description(g: Grievance) -> str:
    return decrypt_str(g.description_enc)
