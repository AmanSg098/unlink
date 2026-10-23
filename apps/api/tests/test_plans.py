from datetime import date, timedelta

import app.routers.plans as plans_router
from app.kpi.library import DEFAULT_WEIGHTS
from app.models import Employee, Grievance, Pip
from tests.conftest import approve_plan, emp_id, make_plan, results


def test_score_ranked_selects_lowest_and_respects_exclusions(login):
    c = login("hr")
    pid = make_plan(c, filters={"departments": ["Eng"]})
    assert c.post(f"/api/plans/{pid}/run").json() == {"pool": 6, "excluded": 2, "algo_selected": 1, "final_selected": 1}
    rows = results(c, pid)
    assert rows["E2"]["final_selected"] and rows["E2"]["rank"] == 1
    assert rows["E1"]["exclusion_reason"] == "On maternity leave" and not rows["E1"]["final_selected"]
    assert rows["E5"]["exclusion_reason"] == "Protected status"
    assert "X1" not in rows and "E6" not in rows


def test_more_exclusions_active_pip_grievance_notice(login, Session):
    c = login("hr")
    with Session() as db:
        e2, e3, e4 = (db.get(Employee, emp_id(db, x)) for x in ("E2", "E3", "E4"))
        db.add(Pip(org_id=1, employee_id=e2.id, reason_category="p", gaps="g" * 10, success_criteria="s" * 10,
                   start_date=date.today() - timedelta(days=5), end_date=date.today() + timedelta(days=30),
                   status="active", proposed_by="x"))
        db.add(Grievance(org_id=1, employee_id=e3.id, category="other", description_enc="enc1:x", logged_by="x",
                         ack_due_on=date.today()))
        e4.status = "on_notice"
        db.commit()
    pid = make_plan(c, filters={"departments": ["Eng"]})
    c.post(f"/api/plans/{pid}/run")
    rows = results(c, pid)
    assert rows["E2"]["exclusion_reason"] == "Active PIP within its end date"
    assert rows["E3"]["exclusion_reason"] == "Open grievance"
    assert rows["E4"]["exclusion_reason"] == "Notice period already started"


def test_cost_target_selects_until_saving_met(login):
    c = login("hr")
    # Each Eng person costs ₹12L; a ₹20L target needs two people.
    pid = make_plan(c, target_count=None, target_cost_paise=2_000_000 * 100, filters={"departments": ["Eng"]})
    assert c.post(f"/api/plans/{pid}/run").json()["algo_selected"] == 2


def test_role_redundancy_and_manual_list(login):
    c = login("hr")
    pid = make_plan(c, selection_method="role_redundancy", eliminated_roles=["Engineer"], weights={},
                    target_count=None)
    c.post(f"/api/plans/{pid}/run")
    sel = {k for k, r in results(c, pid).items() if r["final_selected"]}
    assert sel == {"E2", "E3", "E4"}  # E1 and E5 are Engineers but protected
    pid2 = make_plan(c, selection_method="manual_list", manual_codes=["E1", "E3"], weights={}, target_count=None)
    c.post(f"/api/plans/{pid2}/run")
    rows = results(c, pid2)
    assert rows["E3"]["final_selected"] and not rows["E1"]["final_selected"] and rows["E1"]["excluded"]


def test_validation(login):
    c = login("hr")
    assert c.post("/api/plans", json={"name": "x", "weights": {"performance": 1}}).status_code == 422  # no target
    assert c.post("/api/plans", json={"name": "x", "target_count": 1, "weights": {"bogus": 1}}).status_code == 422
    assert c.post("/api/plans", json={"name": "x", "selection_method": "role_redundancy"}).status_code == 422


def test_override_rules(login):
    c = login("hr")
    pid = make_plan(c, filters={"departments": ["Eng"]})
    c.post(f"/api/plans/{pid}/run")
    rows = results(c, pid)
    r = c.post(f"/api/plans/{pid}/overrides", json={"employee_id": rows["E1"]["employee_id"], "action": "include",
                                                    "justification": "Trying to force it in"})
    assert r.status_code == 422 and "Hard exclusion" in r.json()["detail"]
    assert c.post(f"/api/plans/{pid}/overrides", json={"employee_id": rows["E2"]["employee_id"], "action": "exclude",
                                                       "justification": "short"}).status_code == 422
    ok = c.post(f"/api/plans/{pid}/overrides", json={"employee_id": rows["E2"]["employee_id"], "action": "exclude",
                                                     "justification": "Sole owner of the billing system"})
    assert ok.status_code == 201
    assert not results(c, pid)["E2"]["final_selected"]
    log = login("legal").get("/api/audit", params={"plan_id": pid}).json()
    ov = next(a for a in log if a["action"] == "override_exclude")
    assert ov["before"]["final_selected"] is True and ov["justification"] == "Sole owner of the billing system"


def test_approval_sequence_and_separation_of_duties(login):
    hr, admin = login("hr"), login("admin")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    assert hr.post(f"/api/plans/{pid}/submit").status_code == 409  # not run
    hr.post(f"/api/plans/{pid}/run")
    assert hr.post(f"/api/plans/{pid}/submit").json()["status"] == "submitted"
    assert hr.post(f"/api/plans/{pid}/run").status_code == 409  # locked while submitted
    assert login("finance").post(f"/api/plans/{pid}/decision", json={"approve": True}).status_code == 403  # Legal first
    assert admin.post(f"/api/plans/{pid}/decision", json={"approve": True}).status_code == 200  # admin can act as legal
    r = admin.post(f"/api/plans/{pid}/decision", json={"approve": True})
    assert r.status_code == 403 and "another step" in r.json()["detail"]
    assert login("finance").post(f"/api/plans/{pid}/decision", json={"approve": True}).status_code == 200
    r = login("approver").post(f"/api/plans/{pid}/decision",
                               json={"approve": True, "fairness_justification": "Tiny pool; reviewed"})
    assert r.json()["status"] == "approved"
    steps = [a["step"] for a in login("legal").get(f"/api/plans/{pid}/approvals").json()]
    assert steps == ["legal_review", "finance_review", "final_approval"]


def test_preparer_cannot_approve_and_reject_returns_to_draft(login):
    admin = login("admin")
    pid = make_plan(admin, filters={"departments": ["Eng"]})
    admin.post(f"/api/plans/{pid}/run")
    admin.post(f"/api/plans/{pid}/submit")
    assert admin.post(f"/api/plans/{pid}/decision", json={"approve": True}).status_code == 403
    legal = login("legal")
    assert legal.post(f"/api/plans/{pid}/decision", json={"approve": False}).status_code == 422  # needs comment
    r = legal.post(f"/api/plans/{pid}/decision", json={"approve": False, "comment": "Revisit scope"})
    assert r.json()["status"] == "draft"


def test_fairness_gate_requires_justification(login):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]}, target_count=2)
    hr.post(f"/api/plans/{pid}/run")
    hr.post(f"/api/plans/{pid}/submit")
    login("legal").post(f"/api/plans/{pid}/decision", json={"approve": True})
    login("finance").post(f"/api/plans/{pid}/decision", json={"approve": True})
    f = hr.get(f"/api/plans/{pid}/fairness").json()
    assert "tenure_band" in f["by_attribute"] and "employment_type" in f["by_attribute"]
    if f["any_flagged"]:
        r = login("approver").post(f"/api/plans/{pid}/decision", json={"approve": True})
        assert r.status_code == 409 and "justification" in r.json()["detail"]
    r = login("approver").post(f"/api/plans/{pid}/decision", json={"approve": True, "fairness_justification": "Reviewed"})
    assert r.json()["status"] == "approved"


def test_production_mode_blocks_unverified_rules(login, monkeypatch):
    monkeypatch.setattr(plans_router, "RULESET_MODE", "production")
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    checks = hr.get(f"/api/plans/{pid}/compliance").json()
    assert any("unverified" in c["message"] for c in checks)
    hr.post(f"/api/plans/{pid}/submit")
    login("legal").post(f"/api/plans/{pid}/decision", json={"approve": True})
    login("finance").post(f"/api/plans/{pid}/decision", json={"approve": True})
    r = login("approver").post(f"/api/plans/{pid}/decision", json={"approve": True, "fairness_justification": "x"})
    assert r.status_code == 423


def test_approved_plans_are_immutable_and_versioned(login):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    assert hr.patch(f"/api/plans/{pid}", json={"name": "changed"}).status_code == 409
    v2 = hr.post(f"/api/plans/{pid}/new-version").json()
    assert v2["version"] == 2 and v2["status"] == "draft" and v2["parent_plan_id"] == pid


def test_reports(login):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    assert hr.get(f"/api/plans/{pid}/report.pdf").content.startswith(b"%PDF")
    assert hr.get(f"/api/plans/{pid}/report.pdf", params={"external": True}).status_code == 200
    assert "E2" in hr.get(f"/api/plans/{pid}/export.csv").text


def test_score_ranked_plan_without_weights_uses_defaults(login):
    hr = login("hr")
    r = hr.post("/api/plans", json={"name": "Defaults", "target_count": 1})
    assert r.status_code == 201, r.text
    assert r.json()["weights"] == DEFAULT_WEIGHTS
