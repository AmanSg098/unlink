"""Exit reason codes, their required evidence, employee-facing wording, and the protected-term filter."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.rules import RuleBook
from app.models import Employee, Evidence, ExitCase, Pip, Plan, Review, ReviewCycle


@dataclass(frozen=True)
class ReasonCode:
    code: str
    name: str
    evidence: str  # what's required, in words
    evidence_type: str | None  # uploaded evidence type that satisfies it (when not system-derived)
    wording: str  # employee-facing text (Jinja); Legal approves before first use


CODES: dict[str, ReasonCode] = {c.code: c for c in [
    ReasonCode("RED-ROLE", "Role eliminated", "Approved role-elimination record", "role_elimination_record",
               "your role of {{ role }} has been made redundant as part of an organisational restructuring, and no "
               "suitable alternative role is available"),
    ReasonCode("RED-TEAM", "Team or unit restructured", "Approved restructuring record", "restructuring_record",
               "the {{ department }} team is being restructured and your position does not continue in the new "
               "structure"),
    ReasonCode("RED-LOC", "Location closed or consolidated", "Location decision record", "location_decision",
               "the company is closing or consolidating its {{ location }} location, where your role is based"),
    ReasonCode("PERF-PIP", "Performance not improved after PIP", "Closed PIP with recorded outcome and final review",
               None, "your performance did not reach the standards agreed in your performance improvement plan, "
                     "despite the support provided"),
    ReasonCode("PERF-REVIEW", "Performance below standard (no PIP)", "Review cycles rated below the threshold", None,
               "your performance has remained below the required standard across recent review cycles"),
    ReasonCode("CONDUCT", "Conduct (policy breach)", "Investigation outcome record", "investigation_outcome",
               "an investigation found a breach of company policy"),
    ReasonCode("ATTEND", "Attendance", "Attendance record and any prior warnings", "attendance_record",
               "your attendance has not met the required standard despite prior warnings"),
    ReasonCode("VOLUNTARY", "Voluntary separation or buyout", "Signed acceptance", "signed_acceptance",
               "this follows your acceptance of the voluntary separation offer"),
    ReasonCode("CONTRACT-END", "Fixed-term or contract end", "Contract end date on record", None,
               "your engagement ends on its agreed end date of {{ contract_end_date }}"),
    ReasonCode("OTHER", "Other (legal review required)", "Written justification approved by Legal", None,
               "{{ reason_detail }}"),
]}

REDUNDANCY = {"RED-ROLE", "RED-TEAM", "RED-LOC"}
_env = SandboxedEnvironment(autoescape=False)


# ------------------------------------------------------------------ protected terms

@lru_cache
def _patterns() -> list[tuple[str, str, re.Pattern]]:
    doc = yaml.safe_load((Path(__file__).parent / "protected_terms.yaml").read_text())
    return [(cat, t, re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE))
            for cat, terms in doc["terms"].items() for t in terms]


def protected_terms_in(text: str | None) -> list[str]:
    if not text:
        return []
    return sorted({t for _, t, pat in _patterns() if pat.search(text)})


# ------------------------------------------------------------------ evidence

def evidence_status(db: Session, case: ExitCase, employee: Employee, plan: Plan, book: RuleBook,
                    reason_approved: bool) -> dict:
    """Is the case's reason backed by the evidence its code requires? Returns {ok, requirement, found, missing}."""
    code = CODES.get(case.reason_code or "")
    if code is None:
        return {"ok": False, "requirement": None, "found": [], "missing": "Choose a reason code"}
    found: list[str] = []
    linked = list(db.scalars(select(Evidence).where(Evidence.org_id == case.org_id, Evidence.entity_type == "exit_case",
                                                    Evidence.entity_id == case.id)))
    typed = [e for e in linked if code.evidence_type and e.evidence_type == code.evidence_type]
    found += [f"{e.evidence_type}: {e.filename}" for e in typed]
    ok = bool(typed)

    if code.code in ("RED-ROLE", "RED-TEAM") and plan.status == "approved":
        if code.code == "RED-TEAM" or (plan.selection_method == "role_redundancy" and employee.role in plan.eliminated_roles):
            found.append(f"Approved plan #{plan.id} ({plan.selection_method})")
            ok = True
    elif code.code == "PERF-PIP":
        pip = db.scalar(select(Pip).where(Pip.org_id == case.org_id, Pip.employee_id == employee.id,
                                          Pip.status == "closed", Pip.outcome == "not_met",
                                          Pip.final_review.is_not(None)).order_by(Pip.end_date.desc()))
        if pip:
            found.append(f"PIP #{pip.id} closed as not met on {pip.end_date}")
            ok = True
    elif code.code == "PERF-REVIEW":
        rule = book.value("IN-PERF-001") or {"max_rating": 2, "cycles": 2}
        ratings = db.execute(select(Review.calibrated_rating, ReviewCycle.name)
                             .join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
                             .where(Review.employee_id == employee.id, Review.calibrated_rating.is_not(None))
                             .order_by(ReviewCycle.period_end.desc()).limit(rule["cycles"])).all()
        if len(ratings) >= rule["cycles"] and all(r <= rule["max_rating"] for r, _ in ratings):
            found += [f"{name}: rated {r}" for r, name in ratings]
            ok = True
    elif code.code == "CONTRACT-END":
        if employee.employment_type in ("fixed_term", "contract") and employee.contract_end_date:
            found.append(f"{employee.employment_type} contract ends {employee.contract_end_date}")
            ok = True
    elif code.code == "OTHER":
        ok = bool(case.reason_detail and case.reason_detail.strip()) and reason_approved
        if ok:
            found.append("Justification approved by Legal")
    return {"ok": ok, "requirement": code.evidence, "found": found,
            "missing": None if ok else f"Required: {code.evidence}"}


def wording(case: ExitCase, employee: Employee) -> str:
    code = CODES[case.reason_code]
    return _env.from_string(code.wording).render(
        role=employee.role, department=employee.department, location=employee.location,
        contract_end_date=employee.contract_end_date, reason_detail=case.reason_detail or "")
