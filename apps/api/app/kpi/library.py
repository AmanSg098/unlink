"""KPI library: built-in selection factors plus each org's custom KPIs.

A factor maps an employee (with scoring context: review history, PIP status) to a number; its
direction says whether a higher value raises the retention score.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kpi.custom import evaluate, parse, variables
from app.models import CustomKpi, Employee, Pip, Review, ReviewCycle

DEFAULT_PIP_MAP = {"none": 1.0, "met": 1.0, "partially_met": 0.5, "active": 0.25, "not_met": 0.0}


@dataclass(frozen=True)
class ScoringContext:
    """Per-employee facts the factors need, loaded once per run."""

    as_of: date
    trend: dict[int, float] = field(default_factory=dict)  # employee_id -> avg of last 3 calibrated ratings
    pip_state: dict[int, str] = field(default_factory=dict)  # employee_id -> active | met | partially_met | not_met
    pip_map: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PIP_MAP))

    def pip_value(self, employee_id: int) -> float:
        return self.pip_map.get(self.pip_state.get(employee_id, "none"), 1.0)


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    description: str
    higher_is_better: bool
    extract: Callable[[Employee, ScoringContext], float]


def _tenure_years(e: Employee, sc: ScoringContext) -> float:
    return max((sc.as_of - e.hire_date).days, 0) / 365.25


FACTORS: dict[str, Factor] = {
    f.key: f
    for f in [
        Factor("performance", "Performance", "Calibrated performance rating, last cycle (1-5).", True,
               lambda e, _: e.performance_rating),
        Factor("performance_trend", "Performance trend", "Average calibrated rating over the last three cycles.",
               True, lambda e, sc: sc.trend.get(e.id, e.performance_rating)),
        Factor("potential", "Potential", "Assessed potential rating (1-5).", True, lambda e, _: e.potential_rating),
        Factor("skill_criticality", "Critical skills", "Criticality of the employee's skills to the business (1-5).",
               True, lambda e, _: e.critical_skill_score),
        Factor("tenure", "Tenure", "Years of service as of the plan's data-as-of date.", True, _tenure_years),
        Factor("pip_status", "PIP status", "No PIP or met = 1, partly met = 0.5, active = 0.25, not met = 0.", True,
               lambda e, sc: sc.pip_value(e.id)),
        Factor("cost", "Annual CTC", "Annual cost to company. Higher cost lowers the retention score.", False,
               lambda e, _: e.annual_ctc_paise / 100),
    ]
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "performance": 0.35,
    "performance_trend": 0.10,
    "potential": 0.15,
    "skill_criticality": 0.20,
    "tenure": 0.10,
    "pip_status": 0.10,
    "cost": 0.0,
}


def _custom_factor(k: CustomKpi) -> Factor:
    tree = parse(k.expression)
    return Factor(k.key, k.label, k.description or k.expression, k.higher_is_better,
                  lambda e, sc: evaluate(tree, variables(e, sc.as_of, sc.trend.get(e.id), sc.pip_value(e.id)),
                                         e.custom_metrics or {}))


def get_factors(db: Session, org_id: int) -> dict[str, Factor]:
    """Built-in factors plus the org's active custom KPIs."""
    custom = db.scalars(select(CustomKpi).where(CustomKpi.org_id == org_id, CustomKpi.archived.is_(False)))
    return {**FACTORS, **{k.key: _custom_factor(k) for k in custom}}


def build_scoring_context(db: Session, org_id: int, as_of: date, pip_map: dict | None = None) -> ScoringContext:
    # Performance trend: mean of the last three calibrated ratings per employee (cycles ending by as_of).
    rows = db.execute(
        select(Review.employee_id, Review.calibrated_rating, ReviewCycle.period_end)
        .join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
        .where(Review.org_id == org_id, Review.calibrated_rating.is_not(None), ReviewCycle.period_end <= as_of)
    ).all()
    hist: dict[int, list[tuple[date, float]]] = {}
    for emp, rating, end in rows:
        hist.setdefault(emp, []).append((end, rating))
    trend = {}
    for emp, v in hist.items():
        last3 = [r for _, r in sorted(v, reverse=True)[:3]]
        trend[emp] = sum(last3) / len(last3)

    # PIP state: an active PIP wins; otherwise the most recent closed outcome within the last year.
    pip_state: dict[int, str] = {}
    for p in db.scalars(select(Pip).where(Pip.org_id == org_id, Pip.status.in_(("active", "closed")))
                        .order_by(Pip.start_date)):
        if p.status == "active" and p.start_date <= as_of:
            pip_state[p.employee_id] = "active"
        elif p.status == "closed" and p.outcome and (as_of - p.end_date).days <= 365:
            if pip_state.get(p.employee_id) != "active":
                pip_state[p.employee_id] = p.outcome
    return ScoringContext(as_of=as_of, trend=trend, pip_state=pip_state,
                          pip_map={**DEFAULT_PIP_MAP, **(pip_map or {})})
