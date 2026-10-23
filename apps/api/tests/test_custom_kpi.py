import pytest
from sqlalchemy import select

from app.kpi.custom import KpiError, evaluate, parse
from app.models import Employee
from tests.conftest import make_plan, results

ENV = {"performance_rating": 4.0, "performance_trend": 3.0, "potential_rating": 2.0, "critical_skill_score": 3.0,
       "tenure_years": 10.0, "pip_status_value": 1.0, "annual_ctc": 1000.0}


@pytest.mark.parametrize("expr,expected", [
    ("performance_rating * 2 + potential_rating", 10.0),
    ("(performance_rating + potential_rating) / 2", 3.0),
    ("-tenure_years + 1", -9.0),
    ("min(tenure_years, 5) + max(1, 2, 3)", 8.0),
    ("clamp(annual_ctc / 100, 0, 7)", 7.0),
    ("round(10 / 3, 2)", 3.33),
    ("floor(2.7) + ceil(2.1)", 5.0),
    ("abs(potential_rating - performance_rating)", 2.0),
    ("performance_trend * pip_status_value", 3.0),
    ('metric("csat", 0) * 10', 45.0),
    ('metric("missing", 2.5)', 2.5),
])
def test_evaluate_known_values(expr, expected):
    assert evaluate(parse(expr), ENV, {"csat": 4.5}) == pytest.approx(expected)


@pytest.mark.parametrize("expr", [
    "__import__('os').system('ls')", "performance_rating.__class__", "open('x')", "[1, 2][0]", "annual_ctc ** 2",
    "annual_ctc if annual_ctc else 1", "annual_ctc > 1", "lambda: 1", "unknown_field + 1", "metric(csat, 1)",
    "'text'", "", "1 +", "salary + 1",
])
def test_rejects_unsafe_or_invalid(expr):
    with pytest.raises(KpiError):
        parse(expr)


def test_division_by_zero_is_kpi_error():
    with pytest.raises(KpiError, match="Division by zero"):
        evaluate(parse("annual_ctc / (tenure_years - 10)"), ENV, {})


def test_custom_kpi_end_to_end(login, Session):
    c = login("hr")
    with Session() as db:
        for code, v in {"E2": 5, "E3": 2, "E4": 4, "E6": 3}.items():
            db.scalar(select(Employee).where(Employee.employee_code == code)).custom_metrics = {"csat": v}
        db.commit()
    assert c.post("/api/kpis", json={"key": "performance", "label": "x", "expression": "1"}).status_code == 422
    assert c.post("/api/kpis", json={"key": "bad", "label": "x", "expression": "os.system"}).status_code == 422
    prev = c.post("/api/kpis/preview", json={"expression": 'metric("csat", 3)'}).json()
    assert prev["count"] == 7 and prev["errors"] == 0
    r = c.post("/api/kpis", json={"key": "csat", "label": "CSAT", "expression": 'metric("csat", 3)'})
    assert r.status_code == 201
    pid = make_plan(c, weights={"csat": 1}, filters={"departments": ["Eng"]})
    c.post(f"/api/plans/{pid}/run")
    rows = results(c, pid)
    # Eligible in Eng: M1 (3 default), E2 5, E3 2, E4 4  -> E3 lowest.
    assert rows["E3"]["final_selected"] and rows["E3"]["score"] == 0.0
    assert rows["E2"]["score"] == 100.0
    assert c.get(f"/api/plans/{pid}").json()["kpi_snapshot"]["csat"]["label"] == "CSAT"
    assert c.post(f"/api/kpis/{r.json()['id']}/archive").status_code == 409  # used by an open plan


def test_custom_kpis_are_org_scoped(login):
    login("hr").post("/api/kpis", json={"key": "csat", "label": "CSAT", "expression": "1"})
    assert "csat" not in [k["key"] for k in login("other_org").get("/api/kpis").json()]
