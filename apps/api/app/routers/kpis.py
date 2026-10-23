import statistics
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.db import get_db
from app.deps import HR, Ctx, require
from app.kpi.custom import BASE_FIELDS, KpiError, evaluate, parse, validate_key, variables
from app.kpi.library import DEFAULT_WEIGHTS, FACTORS, build_scoring_context
from app.models import CustomKpi, Employee, Plan
from app.schemas import KpiIn, KpiPreviewIn

router = APIRouter(prefix="/kpis", tags=["kpis"])
VIEW = require("hr", "legal", "finance", "approver", "viewer")


def _custom_out(k: CustomKpi) -> dict:
    return {"key": k.key, "label": k.label, "description": k.description or k.expression,
            "higher_is_better": k.higher_is_better, "default_weight": 0.0, "custom": True, "id": k.id,
            "expression": k.expression, "created_by": k.created_by}


@router.get("")
def list_kpis(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    builtin = [{"key": f.key, "label": f.label, "description": f.description, "higher_is_better": f.higher_is_better,
                "default_weight": DEFAULT_WEIGHTS.get(f.key, 0.0), "custom": False, "id": None, "expression": None,
                "created_by": None} for f in FACTORS.values()]
    custom = db.scalars(select(CustomKpi).where(CustomKpi.org_id == ctx.org_id, CustomKpi.archived.is_(False))
                        .order_by(CustomKpi.id))
    return builtin + [_custom_out(k) for k in custom]


@router.get("/fields")
def kpi_fields(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    metrics: set[str] = set()
    for m in db.scalars(select(Employee.custom_metrics).where(Employee.org_id == ctx.org_id)):
        metrics.update((m or {}).keys())
    return {"fields": BASE_FIELDS, "metrics": sorted(metrics),
            "functions": ["min(a, b, ...)", "max(a, b, ...)", "abs(x)", "round(x, n)", "floor(x)", "ceil(x)",
                          "clamp(x, lo, hi)", 'metric("name", default)']}


@router.post("/preview")
def preview_kpi(body: KpiPreviewIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    """Evaluate an expression over the org's employees without saving it."""
    try:
        tree = parse(body.expression)
    except KpiError as exc:
        raise HTTPException(422, str(exc)) from exc
    today = date.today()
    sc = build_scoring_context(db, ctx.org_id, today, rulebook(db, ctx.org_id).value("IN-PIP-001"))
    values, errors, sample = [], 0, []
    for e in db.scalars(select(Employee).where(Employee.org_id == ctx.org_id).order_by(Employee.employee_code)):
        try:
            v = evaluate(tree, variables(e, today, sc.trend.get(e.id), sc.pip_value(e.id)), e.custom_metrics or {})
        except KpiError:
            errors += 1
            continue
        values.append(v)
        if len(sample) < 5:
            sample.append({"employee_code": e.employee_code, "value": round(v, 4)})
    stats = ({"min": round(min(values), 4), "max": round(max(values), 4),
              "mean": round(statistics.fmean(values), 4)} if values else None)
    return {"count": len(values), "errors": errors, "stats": stats, "sample": sample}


@router.post("", status_code=201)
def create_kpi(body: KpiIn, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    existing = set(db.scalars(select(CustomKpi.key).where(CustomKpi.org_id == ctx.org_id)))
    try:
        validate_key(body.key, set(FACTORS) | existing)
        parse(body.expression)
    except KpiError as exc:
        raise HTTPException(422, str(exc)) from exc
    k = CustomKpi(org_id=ctx.org_id, key=body.key, label=body.label, description=body.description,
                  expression=body.expression.strip(), higher_is_better=body.higher_is_better, created_by=ctx.user)
    db.add(k)
    db.flush()
    audit.record(db, ctx, "kpi", k.id, "create", None,
                 {"key": k.key, "expression": k.expression, "higher_is_better": k.higher_is_better})
    db.commit()
    return _custom_out(k)


@router.post("/{kpi_id}/archive", status_code=204)
def archive_kpi(kpi_id: int, ctx: Ctx = Depends(HR), db: Session = Depends(get_db)):
    k = db.scalar(select(CustomKpi).where(CustomKpi.id == kpi_id, CustomKpi.org_id == ctx.org_id,
                                          CustomKpi.archived.is_(False)))
    if k is None:
        raise HTTPException(404, "KPI not found")
    in_use = [p.name for p in db.scalars(select(Plan).where(Plan.org_id == ctx.org_id,
                                                            Plan.status.in_(("draft", "submitted"))))
              if (p.weights or {}).get(k.key, 0) > 0]
    if in_use:
        raise HTTPException(409, f"KPI is weighted in open plans: {', '.join(in_use)}")
    k.archived = True
    audit.record(db, ctx, "kpi", k.id, "archive", {"archived": False}, {"archived": True})
    db.commit()
