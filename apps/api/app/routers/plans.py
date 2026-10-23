from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, reports
from app.compliance.rules import active_ruleset, rulebook
from app.config import RULESET_MODE
from app.db import get_db
from app.deps import HR, PLAN_VIEWERS, Ctx
from app.documents import PdfUnavailable
from app.kpi.library import DEFAULT_WEIGHTS
from app.models import ExitCase, Plan, PlanOverride, PlanResult, utcnow
from app.plans.service import (
    active_overrides,
    compliance_checks,
    fairness,
    get_plan,
    materialize,
    plan_hash,
    require_draft,
    results_rows,
    validate_weights,
)
from app.schemas import DecisionIn, OverrideIn, PlanIn, PlanPatch, RevokeIn
from app.serialize import to_dict
from app.workflow import approvals

router = APIRouter(prefix="/plans", tags=["plans"])


def _snapshot(p: Plan) -> dict:
    return {"name": p.name, "method": p.selection_method, "target_count": p.target_count,
            "target_cost_paise": p.target_cost_paise, "filters": p.filters, "weights": p.weights,
            "eliminated_roles": p.eliminated_roles, "manual_codes": p.manual_codes, "status": p.status}


def _validate(db: Session, ctx: Ctx, method: str, weights: dict, target_count, target_cost, roles, codes) -> None:
    if method == "score_ranked":
        validate_weights(db, ctx, weights)
        if target_count is None and target_cost is None:
            raise HTTPException(422, "Set a headcount target, a cost-saving target, or both")
    elif weights:
        validate_weights(db, ctx, weights)
    if method == "role_redundancy" and not roles:
        raise HTTPException(422, "List the roles being eliminated")
    if method == "manual_list" and not codes:
        raise HTTPException(422, "List the employee codes for a manual list")


def _plan_out(db: Session, ctx: Ctx, p: Plan) -> dict:
    book = rulebook(db, ctx.org_id, p.ruleset_id)
    step = approvals.current_step(db, ctx.org_id, "plan", p.id)
    return to_dict(p, ruleset={"id": book.ruleset.id, "title": book.ruleset.title, "version": book.ruleset.version,
                               "unverified": len(book.unverified), "total": len(book.rules)} if book.ruleset else None,
                   current_step={"step": step.step, "roles": step.roles} if step else None,
                   cases=db.scalar(select(ExitCase.id).where(ExitCase.plan_id == p.id).limit(1)) is not None)


@router.get("")
def list_plans(ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    return [_plan_out(db, ctx, p) for p in db.scalars(select(Plan).where(Plan.org_id == ctx.org_id)
                                                     .order_by(Plan.id.desc()))]


@router.post("", status_code=201)
def create_plan(body: PlanIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    if body.selection_method == "score_ranked" and not body.weights:
        body.weights = dict(DEFAULT_WEIGHTS)
    _validate(db, ctx, body.selection_method, body.weights, body.target_count, body.target_cost_paise,
              body.eliminated_roles, body.manual_codes)
    rs = active_ruleset(db, ctx.org_id)
    p = Plan(org_id=ctx.org_id, name=body.name, description=body.description, selection_method=body.selection_method,
             target_count=body.target_count, target_cost_paise=body.target_cost_paise,
             filters=body.filters.model_dump(), weights=body.weights, eliminated_roles=body.eliminated_roles,
             manual_codes=body.manual_codes, as_of_date=body.as_of_date or date.today(),
             ruleset_id=rs.id if rs else None, created_by=ctx.user)
    db.add(p)
    db.flush()
    audit.record(db, ctx, "plan", p.id, "create", None, _snapshot(p))
    db.commit()
    return _plan_out(db, ctx, p)


@router.get("/{plan_id}")
def read_plan(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    return _plan_out(db, ctx, get_plan(db, ctx, plan_id))


@router.patch("/{plan_id}")
def update_plan(plan_id: int, body: PlanPatch, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    require_draft(p)
    before = _snapshot(p)
    data = body.model_dump(exclude_unset=True)
    if "filters" in data:
        data["filters"] = body.filters.model_dump()
    merged = {**_snapshot(p), **data}
    _validate(db, ctx, data.get("selection_method", p.selection_method), merged["weights"] or {},
              merged["target_count"], merged["target_cost_paise"], merged["eliminated_roles"], merged["manual_codes"])
    for k, v in data.items():
        setattr(p, k, v)
    audit.record(db, ctx, "plan", p.id, "update", before, _snapshot(p))
    if p.last_run_at is not None:
        materialize(db, ctx, p)
    db.commit()
    return _plan_out(db, ctx, p)


@router.post("/{plan_id}/run")
def run_plan(plan_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    require_draft(p)
    summary = materialize(db, ctx, p)
    audit.record(db, ctx, "plan", p.id, "run", None, summary)
    db.commit()
    return summary


@router.get("/{plan_id}/results")
def plan_results(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    overrides = {o.employee_id: o for o in active_overrides(db, ctx.org_id, p.id)}
    cases = {c.employee_id: c for c in db.scalars(select(ExitCase).where(ExitCase.plan_id == p.id))}
    sensitive = ctx.has("hr", "legal")
    rows = []
    pairs = results_rows(db, ctx, p)
    for r, e in pairs:
        o = overrides.get(e.id)
        c = cases.get(e.id)
        rows.append({
            "employee_id": e.id, "employee_code": e.employee_code, "full_name": e.full_name, "department": e.department,
            "role": e.role, "location": e.location, "hire_date": e.hire_date,
            "annual_ctc_paise": e.annual_ctc_paise if ctx.has("hr", "finance", "legal") else None,
            "score": r.score, "rank": r.rank, "contributions": r.contributions, "algo_selected": r.algo_selected,
            "final_selected": r.final_selected, "excluded": r.excluded,
            "exclusion_reason": r.exclusion_reason if sensitive else ("Protected" if r.excluded else None),
            "override": to_dict(o) if o else None, "case": {"id": c.id, "state": c.state} if c else None,
        })
    rows.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0, x["employee_id"]))
    selected = [x for x in rows if x["final_selected"]]
    summary = {
        "pool": len(rows), "eligible": sum(not x["excluded"] for x in rows), "excluded": sum(x["excluded"] for x in rows),
        "target": p.target_count, "target_cost_paise": p.target_cost_paise,
        "algo_selected": sum(x["algo_selected"] for x in rows), "final_selected": len(selected),
        "overrides": len(overrides),
        # Aggregate saving only; individual pay stays masked for roles that can't see it.
        "annual_cost_reduction_paise": sum(e.annual_ctc_paise for r, e in pairs if r.final_selected)
        if ctx.has("hr", "finance", "legal", "approver") else None,
    }
    return {"summary": summary, "rows": rows}


@router.get("/{plan_id}/fairness")
def plan_fairness(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    return fairness(db, ctx, get_plan(db, ctx, plan_id))


@router.get("/{plan_id}/compliance")
def plan_compliance(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    return compliance_checks(db, ctx, get_plan(db, ctx, plan_id))


@router.post("/{plan_id}/overrides", status_code=201)
def add_override(plan_id: int, body: OverrideIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    require_draft(p)
    r = db.scalar(select(PlanResult).where(PlanResult.org_id == ctx.org_id, PlanResult.plan_id == p.id,
                                           PlanResult.employee_id == body.employee_id))
    if r is None:
        raise HTTPException(404, "Employee is not in this plan's pool (run the plan first)")
    if r.excluded and body.action == "include":
        raise HTTPException(422, f"Hard exclusion cannot be overridden: {r.exclusion_reason}")
    if any(o.employee_id == body.employee_id for o in active_overrides(db, ctx.org_id, p.id)):
        raise HTTPException(409, "An active override already exists for this employee; revoke it first")
    o = PlanOverride(org_id=ctx.org_id, plan_id=p.id, employee_id=body.employee_id, action=body.action,
                     justification=body.justification.strip(), created_by=ctx.user)
    db.add(o)
    db.flush()
    before = {"employee_id": body.employee_id, "final_selected": r.final_selected}
    materialize(db, ctx, p)
    after_sel = db.scalar(select(PlanResult.final_selected).where(PlanResult.plan_id == p.id,
                                                                  PlanResult.employee_id == body.employee_id))
    audit.record(db, ctx, "override", o.id, f"override_{body.action}", before,
                 {"employee_id": body.employee_id, "final_selected": after_sel, "plan_id": p.id}, o.justification)
    db.commit()
    return to_dict(o)


@router.post("/{plan_id}/overrides/{override_id}/revoke", status_code=204)
def revoke_override(plan_id: int, override_id: int, body: RevokeIn, ctx: Ctx = Depends(HR),
                    db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    require_draft(p)
    o = db.scalar(select(PlanOverride).where(PlanOverride.id == override_id, PlanOverride.plan_id == p.id,
                                             PlanOverride.revoked.is_(False)))
    if o is None:
        raise HTTPException(404, "Active override not found")
    o.revoked, o.revoked_by, o.revoked_at = True, ctx.user, utcnow()
    o.revoke_justification = body.justification.strip()
    materialize(db, ctx, p)
    audit.record(db, ctx, "override", o.id, "override_revoke", {"employee_id": o.employee_id, "action": o.action},
                 {"revoked": True, "plan_id": p.id}, o.revoke_justification)
    db.commit()


@router.post("/{plan_id}/submit")
def submit_plan(plan_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    require_draft(p)
    if p.last_run_at is None:
        raise HTTPException(409, "Run the plan before submitting it")
    if not db.scalar(select(PlanResult.id).where(PlanResult.plan_id == p.id, PlanResult.final_selected.is_(True))):
        raise HTTPException(409, "Nobody is selected")
    approvals.start(db, ctx, "plan", p.id, plan_hash(db, ctx, p))
    p.status, p.submitted_by, p.submitted_at = "submitted", ctx.user, utcnow()
    audit.record(db, ctx, "plan", p.id, "submit", {"status": "draft"}, {"status": "submitted"})
    db.commit()
    return _plan_out(db, ctx, p)


@router.post("/{plan_id}/decision")
def decide_plan(plan_id: int, body: DecisionIn, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    if p.status != "submitted":
        raise HTTPException(409, f"Plan is {p.status}")
    step = approvals.current_step(db, ctx.org_id, "plan", p.id)
    if body.approve and step and step.step == "final_approval":
        f = fairness(db, ctx, p)
        if f["any_flagged"] and not (p.fairness_justification or (body.fairness_justification or "").strip()):
            raise HTTPException(409, "The fairness check has unresolved flags; record a justification to approve")
        if RULESET_MODE == "production" and rulebook(db, ctx.org_id, p.ruleset_id).unverified:
            raise HTTPException(423, "The plan's ruleset has unverified rules; production approval is blocked")
        if f["any_flagged"] and body.fairness_justification:
            p.fairness_justification = body.fairness_justification.strip()
            audit.record(db, ctx, "plan", p.id, "fairness_justification", None, {"flags": f["flags"]},
                         p.fairness_justification)
    _, finished = approvals.decide(db, ctx, "plan", p.id, body.approve, body.comment, plan_hash(db, ctx, p))
    if not body.approve:
        p.status = "draft"
        audit.record(db, ctx, "plan", p.id, "returned_to_draft", {"status": "submitted"}, {"status": "draft"},
                     body.comment)
    elif finished:
        p.status, p.approved_at = "approved", utcnow()
        audit.record(db, ctx, "plan", p.id, "approved", {"status": "submitted"}, {"status": "approved"})
    db.commit()
    return _plan_out(db, ctx, p)


@router.get("/{plan_id}/approvals")
def plan_approvals(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    return [to_dict(a) for a in approvals.history(db, ctx.org_id, "plan", p.id)]


@router.post("/{plan_id}/new-version", status_code=201)
def new_version(plan_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    """Approved plans are immutable; changes start a new draft version that needs fresh approval."""
    p = get_plan(db, ctx, plan_id)
    if p.status != "approved":
        raise HTTPException(409, "Only approved plans get new versions; edit drafts directly")
    rs = active_ruleset(db, ctx.org_id)
    n = Plan(org_id=ctx.org_id, name=p.name, description=p.description, selection_method=p.selection_method,
             target_count=p.target_count, target_cost_paise=p.target_cost_paise, filters=p.filters, weights=p.weights,
             eliminated_roles=p.eliminated_roles, manual_codes=p.manual_codes, as_of_date=date.today(),
             ruleset_id=rs.id if rs else p.ruleset_id, version=p.version + 1, parent_plan_id=p.id,
             created_by=ctx.user)
    db.add(n)
    db.flush()
    audit.record(db, ctx, "plan", n.id, "new_version", {"plan_id": p.id, "version": p.version},
                 {"version": n.version})
    db.commit()
    return _plan_out(db, ctx, n)


@router.get("/{plan_id}/export.csv")
def export_plan(plan_id: int, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    data = reports.plan_csv(db, ctx, p)
    audit.record(db, ctx, "plan", p.id, "export_csv")
    db.commit()
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="unlink-plan-{p.id}.csv"'})


@router.get("/{plan_id}/report.pdf")
def report_pdf(plan_id: int, external: bool = False, ctx: Ctx = Depends(PLAN_VIEWERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    if p.last_run_at is None:
        raise HTTPException(409, "Run the plan before generating a report")
    try:
        pdf = reports.defensibility_pdf(db, ctx, p, external)
    except PdfUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    audit.record(db, ctx, "plan", p.id, "report_pdf", None, {"external": external})
    db.commit()
    suffix = "-external" if external else ""
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="unlink-plan-{p.id}{suffix}.pdf"'})
