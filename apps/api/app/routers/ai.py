from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, grievances, notices
from app.ai.drafting import AiError, generate, redact
from app.db import get_db
from app.deps import Ctx, require
from app.exits.service import get_case
from app.exits.states import LABELS
from app.models import AiDraft, Employee, Evidence, ExitCase, NoticeDraft, NoticeTemplate, Plan
from app.plans.service import fairness, get_plan, results_rows
from app.reasons import CODES, protected_terms_in
from app.schemas import ExplainIn, QuestionIn
from app.serialize import to_dict

router = APIRouter(tags=["ai"])
PLAN_DRAFTERS = require("hr", "approver")
CASE_DRAFTERS = require("hr", "legal")


def _run(task: str, data: dict) -> tuple[str, str]:
    try:
        return generate(task, data)
    except AiError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


def _save(db: Session, ctx: Ctx, kind: str, text: str, model: str, *, plan_id=None, case_id=None,
          grievance_id=None, employee_id=None) -> AiDraft:
    d = AiDraft(org_id=ctx.org_id, plan_id=plan_id, exit_case_id=case_id, grievance_id=grievance_id,
                employee_id=employee_id, kind=kind, content=text, model=model, created_by=ctx.user)
    db.add(d)
    db.flush()
    # The audit entry records that a draft was made, by whom, with which model; not the text.
    entity, eid = ("plan", plan_id) if plan_id else ("exit_case", case_id) if case_id else ("grievance", grievance_id)
    audit.record(db, ctx, entity, eid, f"ai_draft_{kind}", None,
                 {"draft_id": d.id, "model": model, "employee_id": employee_id})
    db.commit()
    return d


def _out(d: AiDraft) -> dict:
    return to_dict(d, flagged_terms=protected_terms_in(d.content))


def _factors(p: Plan) -> list[dict]:
    total = sum(w for w in (p.weights or {}).values() if w > 0) or 1
    snap = p.kpi_snapshot or {}
    return [{"key": k, "label": snap.get(k, {}).get("label", k),
             "direction": "higher is better" if snap.get(k, {}).get("higher_is_better", True) else "lower is better",
             "weight_pct": round(w / total * 100, 1)} for k, w in (p.weights or {}).items() if w > 0]


# ------------------------------------------------------------------ plans
@router.get("/plans/{plan_id}/ai/drafts")
def plan_drafts(plan_id: int, ctx: Ctx = Depends(require("hr", "approver", "legal", "finance", "viewer")),
                db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    return [_out(d) for d in db.scalars(select(AiDraft).where(AiDraft.plan_id == p.id).order_by(AiDraft.id.desc()))]


@router.post("/plans/{plan_id}/ai/summary", status_code=201)
def plan_summary(plan_id: int, ctx: Ctx = Depends(PLAN_DRAFTERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    if p.last_run_at is None:
        raise HTTPException(409, "Run the plan first")
    rows = results_rows(db, ctx, p)
    f = fairness(db, ctx, p)
    data = {
        "plan": {"name": p.name, "status": p.status, "rationale": p.description, "method": p.selection_method,
                 "target_roles": p.target_count, "data_as_of": p.as_of_date, "scope": p.filters},
        "scoring_factors": _factors(p),
        "counts": {"in_scope": len(rows), "protected": sum(r.excluded for r, _ in rows),
                   "proposed": sum(r.final_selected for r, _ in rows)},
        "proposed_by_department": Counter(e.department for r, e in rows if r.final_selected),
        "in_scope_by_department": Counter(e.department for _, e in rows),
        "fairness_flags": f["flags"], "fairness_justification": f["justification"],
    }
    task = ("Draft an executive summary memo of this reduction plan for the approval committee: purpose and scope, "
            "how candidates were ranked, outcome against target, fairness observations, and open questions the "
            "reviewers should resolve before approving. Under 500 words.")
    text, model = _run(task, data)
    return _out(_save(db, ctx, "summary", text, model, plan_id=p.id))


@router.post("/plans/{plan_id}/ai/explain", status_code=201)
def explain(plan_id: int, body: ExplainIn, ctx: Ctx = Depends(PLAN_DRAFTERS), db: Session = Depends(get_db)):
    p = get_plan(db, ctx, plan_id)
    row = next(((r, e) for r, e in results_rows(db, ctx, p) if e.id == body.employee_id), None)
    if row is None:
        raise HTTPException(404, "Employee is not in this plan's results")
    r, e = row
    factors = _factors(p)
    data = {
        "employee_code": e.employee_code, "department": e.department, "role": e.role,
        "hard_excluded": r.excluded, "rank": r.rank, "retention_score": r.score,
        "eligible_pool_size": sum(1 for x, _ in results_rows(db, ctx, p) if not x.excluded),
        # position_in_pool: 0 = weakest in the pool on this factor, 1 = strongest (direction applied).
        "factors": [{**f, "contribution_points": r.contributions.get(f["key"]),
                     "position_in_pool": round(r.contributions[f["key"]] / f["weight_pct"], 3)
                     if f["key"] in r.contributions and f["weight_pct"] else None} for f in factors],
        "proposed_by_algorithm": r.algo_selected, "proposed_in_final_plan": r.final_selected,
    }
    task = ("Draft a short plain-language explanation, for an HR reviewer, of how this employee's position in the "
            "ranking was produced: which factors pulled the score up or down and why they are or are not in the "
            "proposed plan. If they are hard-excluded, say only that they are protected from selection. Under 200 words.")
    text, model = _run(task, data)
    return _out(_save(db, ctx, "explanation", text, model, plan_id=p.id, employee_id=e.id))


# ------------------------------------------------------------------ exit cases
@router.get("/exit-cases/{case_id}/ai/drafts")
def case_drafts(case_id: int, ctx: Ctx = Depends(CASE_DRAFTERS), db: Session = Depends(get_db)):
    c = get_case(db, ctx, case_id)
    return [_out(d) for d in db.scalars(select(AiDraft).where(AiDraft.exit_case_id == c.id).order_by(AiDraft.id.desc()))]


@router.post("/exit-cases/{case_id}/ai/notice-draft", status_code=201)
def notice_draft(case_id: int, template_id: int, ctx: Ctx = Depends(CASE_DRAFTERS), db: Session = Depends(get_db)):
    """First draft of a notice from the template and the reason wording. It must still be reviewed and approved."""
    c = get_case(db, ctx, case_id)
    t = db.scalar(select(NoticeTemplate).where(NoticeTemplate.id == template_id, NoticeTemplate.org_id == ctx.org_id))
    if t is None:
        raise HTTPException(404, "Template not found")
    e = db.get(Employee, c.employee_id)
    data = {"template_type": t.type, "template_text": t.body, "merge_fields": notices.merge_field_names(t),
            "employee_code": e.employee_code, "role": e.role, "department": e.department,
            "reason_code": c.reason_code, "reason_wording": CODES[c.reason_code].wording if c.reason_code else None,
            "notice_days": c.notice_days, "pay_in_lieu": c.pay_in_lieu}
    task = ("Rewrite the template text as a clear, humane first draft for this case. Keep every merge field exactly "
            "as written with double braces (for example {{ employee_name }}), keep the meaning and every factual "
            "statement of the template, and add nothing that isn't in the data. Return only the letter body.")
    text, model = _run(task, data)
    return _out(_save(db, ctx, "notice", text, model, case_id=c.id, employee_id=e.id))


@router.post("/exit-cases/{case_id}/ai/drafts/{ai_draft_id}/use", status_code=201)
def use_notice_draft(case_id: int, ai_draft_id: int, ctx: Ctx = Depends(require("hr")), db: Session = Depends(get_db)):
    """Turn an AI notice draft into a new version of the case's current notice draft (still unapproved)."""
    c = get_case(db, ctx, case_id)
    ai = db.scalar(select(AiDraft).where(AiDraft.id == ai_draft_id, AiDraft.exit_case_id == c.id,
                                         AiDraft.kind == "notice"))
    if ai is None:
        raise HTTPException(404, "AI draft not found")
    terms = protected_terms_in(ai.content)
    if terms:
        raise HTTPException(422, f"The AI text contains protected terms ({', '.join(terms)}); edit it manually instead")
    current = db.scalar(select(NoticeDraft).where(NoticeDraft.exit_case_id == c.id,
                                                  NoticeDraft.status.in_(("draft", "in_batch")))
                        .order_by(NoticeDraft.id.desc()))
    if current is None:
        raise HTTPException(409, "Create a notice draft from a template first")
    t = db.get(NoticeTemplate, current.template_id)
    vals, problems = notices.merge_values(db, c)
    tmp = NoticeTemplate(subject=current.subject, body=ai.content)
    try:
        _, body, _ = notices.render_template(tmp, vals, problems)
    except Exception as exc:  # malformed placeholders from the model
        raise HTTPException(422, f"The AI text couldn't be merged: {type(exc).__name__}") from exc
    nd = notices.edit_draft(db, ctx, current, current.subject, body)
    audit.record(db, ctx, "exit_case", c.id, "ai_draft_used", None, {"ai_draft_id": ai.id, "notice_draft_id": nd.id,
                                                                     "template": t.key})
    db.commit()
    return to_dict(nd)


@router.post("/exit-cases/{case_id}/ai/reply", status_code=201)
def reply(case_id: int, body: QuestionIn, ctx: Ctx = Depends(require("hr")), db: Session = Depends(get_db)):
    c = get_case(db, ctx, case_id)
    e = db.get(Employee, c.employee_id)
    data = {"employee_code": e.employee_code, "case_stage": LABELS.get(c.state, c.state),
            "notice_date": c.notice_date, "notice_days": c.notice_days, "pay_in_lieu": c.pay_in_lieu,
            "last_working_day": c.actual_last_day or c.last_working_day, "reason_code": c.reason_code,
            "question": redact(body.question, [e.full_name], e.employee_code)}
    task = ("Draft a short, kind reply from HR to this employee question, using only the case facts given. "
            "Don't state any amounts; point to the FNF statement for money questions. If a fact needed to answer "
            "isn't in the data, say HR will confirm. Under 150 words.")
    text, model = _run(task, data)
    return _out(_save(db, ctx, "reply", text, model, case_id=c.id, employee_id=e.id))


@router.post("/grievances/{grievance_id}/ai/summary", status_code=201)
def grievance_summary(grievance_id: int, ctx: Ctx = Depends(CASE_DRAFTERS), db: Session = Depends(get_db)):
    g = grievances.get(db, ctx, grievance_id)
    e = db.get(Employee, g.employee_id)
    case = db.get(ExitCase, g.exit_case_id)
    sources = [f"{v.evidence_type}: {v.filename}" for v in db.scalars(select(Evidence).where(
        Evidence.entity_type == "exit_case", Evidence.entity_id == case.id))] if case else []
    data = {"grievance_ref": grievances.ref(g), "category": g.category, "case_stage": case.state if case else None,
            "reason_code": case.reason_code if case else None,
            "description": redact(grievances.description(g), [e.full_name], e.employee_code),
            "source_documents": sources}
    task = ("Summarise this grievance for the reviewer: the specific concerns raised, what each would need to be "
            "checked against, and which listed source documents look relevant. Don't judge the outcome. Under 250 words.")
    text, model = _run(task, data)
    return _out(_save(db, ctx, "grievance_summary", text, model, grievance_id=g.id, employee_id=e.id))
