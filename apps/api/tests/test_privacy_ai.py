import ast
import logging
from pathlib import Path

import pytest

import app.routers.ai as ai_router
from app.ai.drafting import AiError, redact
from tests.conftest import approve_plan, make_plan, results

APP = Path(__file__).parents[1] / "app"
PII = ("Person E2", "1200000", "120000000", "Male", "Female", "maternity", "p.e2@example.com", "e2@one.in")


@pytest.fixture
def captured(monkeypatch):
    seen: list[dict] = []

    def fake_generate(task, data):
        seen.append(data)
        return "Draft text", "claude-opus-5-5"

    monkeypatch.setattr(ai_router, "generate", fake_generate)
    return seen


def _approved_case(login):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    return pid, hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]


def test_ai_prompts_carry_no_pii(login, captured):
    pid, cid = _approved_case(login)
    hr = login("hr")
    e2 = results(hr, pid)["E2"]["employee_id"]
    before = results(hr, pid)
    assert hr.post(f"/api/plans/{pid}/ai/summary").status_code == 201
    assert hr.post(f"/api/plans/{pid}/ai/explain", json={"employee_id": e2}).status_code == 201
    tid = hr.get("/api/notice-templates").json()[0]["id"]
    assert hr.post(f"/api/exit-cases/{cid}/ai/notice-draft", params={"template_id": tid}).status_code == 201
    assert hr.post(f"/api/exit-cases/{cid}/ai/reply",
                   json={"question": "Hi, this is Person E2 (e2@one.in), when is my last day?"}).status_code == 201
    hr.post("/api/grievances", json={"exit_case_id": cid, "category": "fnf",
                                     "description": "Person E2 here, call me on 98765 43210 about my pay"})
    gid = hr.get("/api/grievances").json()[0]["id"]
    assert login("legal").post(f"/api/grievances/{gid}/ai/summary").status_code == 201
    blob = str(captured)
    for leaked in PII:
        assert leaked not in blob, leaked
    assert "98765" not in blob and "E2" in blob
    assert results(hr, pid) == before  # drafting never changes selection


def test_ai_errors_and_roles(login, monkeypatch):
    def boom(task, data):
        raise AiError(503, "AI drafting is not configured")

    monkeypatch.setattr(ai_router, "generate", boom)
    pid, _ = _approved_case(login)
    r = login("hr").post(f"/api/plans/{pid}/ai/summary")
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    assert login("viewer").post(f"/api/plans/{pid}/ai/summary").status_code == 403


def test_redact():
    out = redact("Anita Mehta (anita@x.com, +91 98765 43210) said Anita was upset", ["Anita Mehta"], "E0206")
    assert "Anita" not in out and "Mehta" not in out and "98765" not in out and "[email]" in out


@pytest.mark.parametrize("pkg", ["scoring", "fairness", "workflow", "kpi", "fnf", "exits", "compliance", "notices",
                                 "reasons", "performance"])
def test_ai_never_in_decision_or_sending_paths(pkg):
    for f in (APP / pkg).rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n.startswith(("app.ai", "anthropic")) for n in names), f"{f} imports {names}"


def test_no_pii_in_application_logs(login, caplog):
    caplog.set_level(logging.DEBUG)
    pid, cid = _approved_case(login)
    hr = login("hr")
    hr.get("/api/employees")
    hr.get(f"/api/exit-cases/{cid}")
    text = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    for leaked in PII:
        assert leaked not in text, leaked
