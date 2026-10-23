import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import ExitCase, NoticeBatch
from tests.conftest import approve_plan, make_plan


@pytest.fixture
def case_ids(login):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]}, target_count=2)
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    return {c["employee"]["employee_code"]: c["id"] for c in hr.post("/api/exit-cases", json={"plan_id": pid}).json()}


def _employee_client(login, mails, case_id) -> TestClient:
    hr = login("hr")
    assert hr.post(f"/api/exit-cases/{case_id}/invite").status_code == 200
    token = re.search(r"token=([\w-]+)", mails()[-1]["text"]).group(1)
    public = TestClient(app)
    r = public.post("/api/auth/activate", json={"token": token, "password": "a-good-password"})
    assert r.status_code == 200, r.text
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": r.json()["email"], "password": "a-good-password"}).status_code == 200
    return c


def test_self_service_sees_only_own_case(login, mails, case_ids):
    emp = _employee_client(login, mails, case_ids["E2"])
    me = emp.get("/api/auth/me").json()
    assert me["kind"] == "employee" and me["employee_code"] == "E2"
    case = emp.get("/api/me/case").json()
    assert case["state"] == "identified" and "score" not in str(case) and "plan" not in case
    assert emp.get("/api/plans").status_code == 403
    assert emp.get("/api/employees").status_code == 403
    assert emp.get(f"/api/exit-cases/{case_ids['E3']}").status_code == 403


def test_grievance_holds_case_and_prepares_acknowledgement(login, mails, case_ids, Session):
    emp = _employee_client(login, mails, case_ids["E2"])
    r = emp.post("/api/me/grievances", json={"category": "selection", "description": "I think my scores were wrong."})
    assert r.status_code == 201
    with Session() as db:
        case = db.get(ExitCase, case_ids["E2"])
        assert case.state == "on_hold" and "Grievance" in case.hold_reason
        batch = db.scalar(select(NoticeBatch).where(NoticeBatch.name.like("Grievance acknowledgement%")))
        assert batch is not None and batch.status == "draft"  # a person must still approve and release it
    hr = login("hr")
    gid = hr.get("/api/grievances").json()[0]["id"]
    assert "scores were wrong" in hr.get(f"/api/grievances/{gid}").json()["description"]
    # The person who owns the case can't decide the grievance.
    r = hr.post(f"/api/grievances/{gid}/decision", json={"findings": "Checked", "outcome": "rejected",
                                                         "reasons": "Scores were correct"})
    assert r.status_code == 403
    legal = login("legal")
    assert legal.post(f"/api/grievances/{gid}/decision", json={"findings": "Checked inputs",
                                                               "outcome": "rejected",
                                                               "reasons": "Scores match the review records"}).status_code == 200
    assert emp.post(f"/api/me/grievances/{gid}/appeal", json={"grounds": "The review data is outdated"}).status_code == 201
    assert emp.post(f"/api/me/grievances/{gid}/appeal", json={"grounds": "Again please"}).status_code == 409
    r = legal.post(f"/api/grievances/{gid}/appeal/decision", json={"outcome": "rejected", "reasons": "x" * 10})
    assert r.status_code == 403  # same person as the original decision
    assert login("legal2").post(f"/api/grievances/{gid}/appeal/decision",
                                json={"outcome": "partly_upheld", "reasons": "Data refreshed"}).json()["status"] == "closed"
    # Hold can be released only once no grievance is open.
    assert login("legal2").post(f"/api/exit-cases/{case_ids['E2']}/release-hold",
                                json={"text": "Grievance closed"}).status_code == 200


def test_release_hold_blocked_while_grievance_open(login, case_ids):
    hr = login("hr")
    hr.post("/api/grievances", json={"exit_case_id": case_ids["E3"], "category": "process",
                                     "description": "Employee says no consultation took place."})
    r = login("legal").post(f"/api/exit-cases/{case_ids['E3']}/release-hold", json={"text": "Release"})
    assert r.status_code == 409
