"""Reduction plans: scoring, selection by method, overrides, fairness, compliance checks, approval content."""

import logging
from collections import defaultdict
from dataclasses import replace
from datetime import date

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.compliance.rules import RuleBook, rulebook
from app.crypto import content_hash
from app.deps import Ctx
from app.fairness.adverse_impact import adverse_impact
from app.kpi.custom import KpiError
from app.kpi.library import build_scoring_context, get_factors
from app.models import Employee, Org, Plan, PlanOverride, PlanResult, utcnow
from app.scoring.engine import Candidate, ScoredCandidate, apply_overrides, normalize_weights, score_pool
from app.scoring.exclusions import build_context, hard_exclusion_reason

log = logging.getLogger(__name__)

FAIRNESS_THRESHOLD = 0.8
FAIRNESS_ATTRIBUTES = ["gender", "age_band", "department", "location", "employment_type", "tenure_band"]
MIN_GROUP = 5


def get_plan(db: Session, ctx: Ctx, plan_id: int) -> Plan:
    p = db.scalar(select(Plan).where(Plan.id == plan_id, Plan.org_id == ctx.org_id))
    if p is None:
        raise HTTPException(404, "Plan not found")
    return p


def require_draft(p: Plan) -> None:
    if p.status != "draft":
        raise HTTPException(409, f"Plan is {p.status}; only drafts can be changed")


def validate_weights(db: Session, ctx: Ctx, weights: dict[str, float]) -> None:
    try:
        normalize_weights(weights, list(get_factors(db, ctx.org_id)))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def pool_query(org_id: int, p: Plan):
    q = select(Employee).where(Employee.org_id == org_id)
    f = p.filters or {}
    if f.get("departments"):
        q = q.where(Employee.department.in_(f["departments"]))
    if f.get("locations"):
        q = q.where(Employee.location.in_(f["locations"]))
    if f.get("roles"):
        q = q.where(Employee.role.in_(f["roles"]))
    return q


def active_overrides(db: Session, org_id: int, plan_id: int) -> list[PlanOverride]:
    return list(db.scalars(select(PlanOverride).where(PlanOverride.org_id == org_id, PlanOverride.plan_id == plan_id,
                                                      PlanOverride.revoked.is_(False))))


def _book(db: Session, org_id: int, p: Plan) -> RuleBook:
    return rulebook(db, org_id, p.ruleset_id)


def materialize(db: Session, ctx: Ctx, p: Plan) -> dict:
    """Score the pool, select by the plan's method and targets, apply overrides, persist results."""
    book = _book(db, ctx.org_id, p)
    factors = get_factors(db, ctx.org_id)
    weights = p.weights or {}
    used = {k: f for k, f in factors.items() if weights.get(k, 0) > 0}
    missing = [k for k, w in weights.items() if w > 0 and k not in factors]
    if missing:
        raise HTTPException(422, f"Plan uses KPIs that no longer exist: {', '.join(missing)}")

    protected = frozenset((book.value("IN-PROTECT-001") or {}).get("leave_types") or ["maternity", "medical"])
    xc = build_context(db, ctx.org_id, p.as_of_date, protected)
    sc = build_scoring_context(db, ctx.org_id, p.as_of_date, book.value("IN-PIP-001"))

    employees = list(db.scalars(pool_query(ctx.org_id, p)))
    by_id = {e.id: e for e in employees}
    candidates = []
    for e in employees:
        reason = hard_exclusion_reason(e, xc)
        try:
            values = {k: f.extract(e, sc) for k, f in used.items()}
        except KpiError as exc:
            raise HTTPException(422, f"KPI evaluation failed for employee {e.employee_code}: {exc}") from exc
        candidates.append(Candidate(employee_id=e.id, values=values, excluded=reason is not None,
                                    exclusion_reason=reason))
    if used:
        try:
            scored = score_pool(candidates, weights, {k: f.higher_is_better for k, f in factors.items()}, 0)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        # Role-redundancy and manual-list plans may run without weights; nobody is scored then.
        if p.selection_method == "score_ranked":
            raise HTTPException(422, "at least one weight must be positive")
        scored = [ScoredCandidate(employee_id=c.employee_id, score=None, rank=None, excluded=c.excluded,
                                  exclusion_reason=c.exclusion_reason)
                  for c in sorted(candidates, key=lambda c: c.employee_id)]

    eligible = [s for s in scored if not s.excluded]
    if p.selection_method == "role_redundancy":
        roles = set(p.eliminated_roles or [])
        algo = {s.employee_id for s in eligible if by_id[s.employee_id].role in roles}
    elif p.selection_method == "manual_list":
        codes = set(p.manual_codes or [])
        algo = {s.employee_id for s in eligible if by_id[s.employee_id].employee_code in codes}
    else:
        algo = set()
        saved = 0
        for s in eligible:  # ascending score
            count_met = p.target_count is None or len(algo) >= p.target_count
            cost_met = p.target_cost_paise is None or saved >= p.target_cost_paise
            if count_met and cost_met:
                break
            algo.add(s.employee_id)
            saved += by_id[s.employee_id].annual_ctc_paise

    scored = [replace(s, selected=s.employee_id in algo) for s in scored]
    overrides = {o.employee_id: o.action for o in active_overrides(db, ctx.org_id, p.id)}
    final = apply_overrides(scored, overrides)

    db.execute(delete(PlanResult).where(PlanResult.org_id == ctx.org_id, PlanResult.plan_id == p.id))
    for s in scored:
        db.add(PlanResult(org_id=ctx.org_id, plan_id=p.id, employee_id=s.employee_id, score=s.score, rank=s.rank,
                          contributions=s.contributions, algo_selected=s.selected, final_selected=final[s.employee_id],
                          excluded=s.excluded, exclusion_reason=s.exclusion_reason))
    p.last_run_at = utcnow()
    if p.ruleset_id is None and book.ruleset is not None:
        p.ruleset_id = book.ruleset.id
    p.kpi_snapshot = {k: {"label": f.label, "description": f.description, "higher_is_better": f.higher_is_better}
                      for k, f in used.items()}
    db.flush()
    summary = {"pool": len(scored), "excluded": sum(s.excluded for s in scored),
               "algo_selected": len(algo), "final_selected": sum(final.values())}
    log.info("plan %s materialized: %s", p.id, summary)
    return summary


def results_rows(db: Session, ctx: Ctx, p: Plan) -> list[tuple[PlanResult, Employee]]:
    return db.execute(select(PlanResult, Employee).join(Employee, Employee.id == PlanResult.employee_id)
                      .where(PlanResult.org_id == ctx.org_id, PlanResult.plan_id == p.id)).all()


def approval_content(db: Session, ctx: Ctx, p: Plan) -> dict:
    """Everything an approver signs off on. Any change to it invalidates the approval."""
    rows = results_rows(db, ctx, p)
    return {
        "name": p.name, "description": p.description, "method": p.selection_method, "filters": p.filters,
        "weights": p.weights, "targets": [p.target_count, p.target_cost_paise], "eliminated_roles": p.eliminated_roles,
        "manual_codes": p.manual_codes, "as_of": p.as_of_date, "ruleset_id": p.ruleset_id,
        "selected": sorted(r.employee_id for r, _ in rows if r.final_selected),
        "overrides": sorted((o.employee_id, o.action) for o in active_overrides(db, ctx.org_id, p.id)),
    }


def plan_hash(db: Session, ctx: Ctx, p: Plan) -> str:
    return content_hash(approval_content(db, ctx, p))


# ------------------------------------------------------------------ fairness

def tenure_band(e: Employee, as_of: date) -> str:
    y = (as_of - e.hire_date).days / 365.25
    return "<1 yr" if y < 1 else "1-3 yrs" if y < 3 else "3-5 yrs" if y < 5 else "5-10 yrs" if y < 10 else "10+ yrs"


def fairness(db: Session, ctx: Ctx, p: Plan) -> dict:
    rows = results_rows(db, ctx, p)

    def attr(e: Employee, a: str) -> str:
        return tenure_band(e, p.as_of_date) if a == "tenure_band" else getattr(e, a)

    by_attribute = {a: [vars(g) for g in adverse_impact(((attr(e, a), r.final_selected) for r, e in rows),
                                                        threshold=FAIRNESS_THRESHOLD, min_group_size=MIN_GROUP)]
                    for a in FAIRNESS_ATTRIBUTES}
    inter = [vars(g) for g in adverse_impact(((f"{e.gender} · {e.age_band}", r.final_selected) for r, e in rows),
                                             threshold=FAIRNESS_THRESHOLD, min_group_size=MIN_GROUP)]
    inter = [g for g in inter if g["pool"] >= MIN_GROUP]
    flagged = [f"{a}: {g['group']}" for a, gs in by_attribute.items() for g in gs
               if g["flagged"] and not g["small_sample"]]
    flagged += [f"gender × age band: {g['group']}" for g in inter if g["flagged"]]
    return {"threshold": FAIRNESS_THRESHOLD, "by_attribute": by_attribute, "intersectional": inter,
            "any_flagged": bool(flagged), "flags": flagged, "justification": p.fairness_justification}


# ------------------------------------------------------------------ compliance checks

def compliance_checks(db: Session, ctx: Ctx, p: Plan) -> list[dict]:
    """Rule-based checks shown on the plan. severity: info | warning | block."""
    from app.config import RULESET_MODE

    book = _book(db, ctx.org_id, p)
    out: list[dict] = []
    if book.ruleset is None:
        return [{"rule": None, "severity": "warning", "message": "No jurisdiction ruleset is loaded."}]
    if book.unverified:
        out.append({"rule": None, "severity": "block" if RULESET_MODE == "production" else "warning",
                    "message": f"{len(book.unverified)} rules in {book.ruleset.title} v{book.ruleset.version} are "
                               "unverified: not for use with real employees."})
    rows = results_rows(db, ctx, p)
    selected = [e for r, e in rows if r.final_selected]
    org = db.get(Org, ctx.org_id)
    size = int((org.settings or {}).get("establishment_size", 0))
    govt = book.value("IN-GOVT-001") or {}
    if govt and size >= govt.get("min_workers", 10**9) and selected:
        out.append({"rule": "IN-GOVT-001", "severity": "warning",
                    "message": f"Establishment size {size} meets the {govt['min_workers']}-worker threshold: prior "
                               f"government permission is needed at least {govt['apply_days_before']} days before "
                               "retrenchment for redundancy reasons."})
    consult = book.value("IN-CONSULT-001") or {}
    if consult and len(selected) >= consult.get("min_group_size", 10**9):
        out.append({"rule": "IN-CONSULT-001", "severity": "info",
                    "message": f"{len(selected)} people selected: a pre-notice consultation is required at least "
                               f"{consult['days_before_notice']} days before termination notices are released."})
    # Last come, first go within department + role: a selected person hired earlier than a retained eligible peer.
    retained = defaultdict(list)
    for r, e in rows:
        if not r.final_selected and not r.excluded:
            retained[(e.department, e.role)].append(e)
    deviations = 0
    for e in selected:
        if any(o.hire_date > e.hire_date for o in retained[(e.department, e.role)]):
            deviations += 1
    if deviations and book.get("IN-RETR-002"):
        out.append({"rule": "IN-RETR-002", "severity": "warning",
                    "message": f"{deviations} selected people joined before someone retained in the same department "
                               "and role. For redundancy exits, record why 'last come, first go' isn't followed."})
    return out
