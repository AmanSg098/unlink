from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

import app.storage as storage_mod
from app.models import Employee, EmployeeHistory, Evidence
from tests.conftest import emp_id

PDF = b"%PDF-1.4\n%fake\n"


def test_private_checkin_notes_only_for_author(login, Session):
    m = login("manager")
    e2 = emp_id(Session, "E2")
    r = m.post("/api/performance/checkins", json={"employee_id": e2, "scheduled_for": "2026-10-01",
                                                   "summary": "Talked priorities", "private_note": "Seems stressed",
                                                   "actions": [{"text": "Pair on tickets", "owner": "mo@one.in"}]})
    assert r.status_code == 201
    mine = m.get("/api/employees/by-code/E2").json()["checkins"][0]
    assert mine["private_note"] == "Seems stressed" and len(mine["actions"]) == 1
    hr_view = login("hr").get("/api/employees/by-code/E2").json()["checkins"][0]
    assert hr_view["private_note"] is None and hr_view["has_private_note"] is True


def test_manager_scope(login, Session):
    m = login("manager")
    r = m.post("/api/performance/goals", json={"employee_id": emp_id(Session, "E6"), "title": "x"})
    assert r.status_code == 404  # E6 isn't in their reporting line
    assert m.post("/api/performance/goals", json={"employee_id": emp_id(Session, "E2"), "title": "Ship v2"}).status_code == 201


def test_pip_lifecycle_and_close_rules(login, Session):
    m, hr = login("manager"), login("hr")
    body = {"employee_id": emp_id(Session, "E2"), "reason_category": "performance", "gaps": "Missed targets twice",
            "success_criteria": "Hit 90% of weekly targets", "start_date": str(date.today() - timedelta(days=60))}
    p = m.post("/api/performance/pips", json=body).json()
    assert p["status"] == "proposed"
    assert m.post(f"/api/performance/pips/{p['id']}/activate").status_code == 403
    assert hr.post(f"/api/performance/pips/{p['id']}/activate").json()["status"] == "active"
    close = {"outcome": "not_met", "final_review": "Final review held; targets not met", "final_review_on": str(date.today())}
    r = hr.post(f"/api/performance/pips/{p['id']}/close", json=close)
    assert r.status_code == 409 and "two dated check-ins" in r.json()["detail"]
    for d in (20, 40):
        m.post(f"/api/performance/pips/{p['id']}/milestones",
               json={"on_date": str(date.today() - timedelta(days=60 - d)), "evidence_reviewed": "Target sheet",
                     "outcome": "not_met"})
    assert hr.post(f"/api/performance/pips/{p['id']}/ack", json={"status": "declined"}).json()["employee_ack"] == "declined"
    assert hr.post(f"/api/performance/pips/{p['id']}/close", json=close).json()["outcome"] == "not_met"


def test_calibration_sets_current_rating(login, Session):
    hr = login("hr")
    cyc = hr.post("/api/performance/cycles", json={"name": "Q4", "period_start": "2026-10-01",
                                                   "period_end": "2026-12-31"}).json()
    e2 = emp_id(Session, "E2")
    rev = hr.put(f"/api/performance/cycles/{cyc['id']}/reviews", json={"employee_id": e2, "manager_rating": 3}).json()
    assert hr.post(f"/api/performance/cycles/{cyc['id']}/close").status_code == 409  # not calibrated
    hr.post(f"/api/performance/reviews/{rev['id']}/calibrate", json={"calibrated_rating": 3.5})
    detail = hr.get(f"/api/performance/cycles/{cyc['id']}").json()
    assert detail["calibration"]["departments"]["Eng"]["count"] == 1
    assert hr.post(f"/api/performance/cycles/{cyc['id']}/close").json()["ratings_updated"] == 1
    with Session() as db:
        assert db.get(Employee, e2).performance_rating == 3.5
        h = db.scalar(select(EmployeeHistory).where(EmployeeHistory.employee_id == e2))
        assert (h.field, h.old_value, h.new_value) == ("performance_rating", 2.0, 3.5)


def test_evidence_upload_checks_and_encryption(login, Session):
    hr = login("hr")
    cyc = hr.post("/api/performance/cycles", json={"name": "Q", "period_start": "2026-01-01",
                                                   "period_end": "2026-03-31"}).json()
    rev = hr.put(f"/api/performance/cycles/{cyc['id']}/reviews",
                 json={"employee_id": emp_id(Session, "E2"), "manager_rating": 2}).json()
    form = {"entity_type": "review", "entity_id": str(rev["id"]), "evidence_type": "review_form"}
    assert hr.post("/api/performance/evidence", data=form, files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    assert hr.post("/api/performance/evidence", data=form, files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 422
    ok = hr.post("/api/performance/evidence", data=form, files={"file": ("review.pdf", PDF, "application/pdf")})
    assert ok.status_code == 201 and ok.json()["scan_status"] == "not_scanned"
    with Session() as db:
        ev = db.scalar(select(Evidence))
        raw = (Path(storage_mod.FILES_DIR) / ev.storage_key).read_bytes()
        assert PDF not in raw  # stored encrypted
    dl = hr.get(f"/api/employees/evidence/{ok.json()['id']}/download")
    assert dl.content == PDF


def test_missing_evidence_report(login):
    rows = login("hr").get("/api/performance/missing-evidence").json()
    codes = {r["employee_code"] for r in rows}
    assert "E2" in codes and "E4" not in codes
