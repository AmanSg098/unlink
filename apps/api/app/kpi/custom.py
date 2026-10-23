"""Custom KPI expressions over one employee, built on the shared safe expression language.

Fields: the base fields below. Imported metrics: metric("name", default). See compliance/expr.py.
"""

import ast
import re
from collections.abc import Mapping
from datetime import date

from app.compliance.expr import ExprError, evaluate as _evaluate, parse as _parse
from app.models import Employee

KpiError = ExprError
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

BASE_FIELDS = {
    "performance_rating": "Calibrated performance rating, last cycle (1-5)",
    "performance_trend": "Average calibrated rating over the last three cycles (1-5)",
    "potential_rating": "Potential rating (1-5)",
    "critical_skill_score": "Critical skill score (1-5)",
    "tenure_years": "Years of service at the plan's data-as-of date",
    "pip_status_value": "PIP status mapped to 0-1 (1 = no PIP or PIP met)",
    "annual_ctc": "Annual CTC in rupees",
}


def parse(expression: str) -> ast.Expression:
    return _parse(expression, BASE_FIELDS, allow_metric=True)


def evaluate(tree: ast.Expression, env: Mapping[str, float], metrics: Mapping[str, float]) -> float:
    return _evaluate(tree, env, metrics)


def variables(e: Employee, as_of: date, perf_trend: float | None = None, pip_value: float = 1.0) -> dict[str, float]:
    return {
        "performance_rating": e.performance_rating,
        "performance_trend": perf_trend if perf_trend is not None else e.performance_rating,
        "potential_rating": e.potential_rating,
        "critical_skill_score": e.critical_skill_score,
        "tenure_years": max((as_of - e.hire_date).days, 0) / 365.25,
        "pip_status_value": pip_value,
        "annual_ctc": e.annual_ctc_paise / 100,
    }


def validate_key(key: str, reserved: set[str]) -> None:
    if not KEY_RE.match(key):
        raise KpiError("Key must be lowercase letters, digits, underscores (2-41 chars), starting with a letter")
    if key in reserved:
        raise KpiError(f"Key '{key}' is already used")
