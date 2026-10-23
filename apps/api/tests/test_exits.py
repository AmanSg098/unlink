import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select

import app.storage as storage_mod
from app.models import AuditLog, Document, Employee, ExitCase, ExitTask
from tests.conftest import approve_plan, approve_templates_and_wording, emp_id, make_plan, template_id


@pytest.fixture
def sent_case(login, Session, run_jobs):
    """E2's case after a termination notice was released with pay in lieu (so the last day is set)."""
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]}, target_count=1)
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    case_id = hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]
    hr.post(f"/api/exit-cases/{case_id}/reason", json={"reason_code": "RED-TEAM"})
    hr.post(f"/api/exit-cases/{case_id}/dates", json={"notice_date": str(date.today()), "pay_in_lieu": True})
    approve_templates_and_wording(login, Session)
    d = hr.post(f"/api/plans/{pid}/notice-drafts", json={"template_id": template_id(hr, "termination_notice")}).json()
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": [x["id"] for x in d]}).json()
    hr.post(f"/api/notice-batches/{b['id']}/submit")
    login("approver").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True})
    hr.post(f"/api/notice-batches/{b['id']}/release")
    run_jobs()
    with Session() as db:
        assert db.get(ExitCase, case_id).state == "last_day_set"
    return case_id


def test_reason_rules(login, Session):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    cid = hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]
    r = hr.post(f"/api/exit-cases/{cid}/reason", json={"reason_code": "RED-TEAM", "reason_detail": "She is pregnant"})
    assert r.status_code == 422 and "pregnant" in r.json()["detail"]
    hr.post(f"/api/exit-cases/{cid}/reason", json={"reason_code": "CONDUCT"})
    ev = hr.get(f"/api/exit-cases/{cid}").json()["reason"]["evidence"]
    assert not ev["ok"] and "Investigation outcome" in ev["missing"]
    up = hr.post(f"/api/exit-cases/{cid}/evidence", data={"evidence_type": "investigation_outcome"},
                 files={"file": ("outcome.txt", b"Investigation concluded.", "text/plain")})
    assert up.status_code == 201
    assert hr.get(f"/api/exit-cases/{cid}").json()["reason"]["evidence"]["ok"]
    hr.post(f"/api/exit-cases/{cid}/reason", json={"reason_code": "PERF-PIP"})
    assert not hr.get(f"/api/exit-cases/{cid}").json()["reason"]["evidence"]["ok"]  # no closed PIP
    hr.post(f"/api/exit-cases/{cid}/reason", json={"reason_code": "OTHER",
                                                   "reason_detail": "Business closure of the client account she served"})
    assert not hr.get(f"/api/exit-cases/{cid}").json()["reason"]["evidence"]["ok"]
    login("legal").post(f"/api/exit-cases/{cid}/reason/decision", json={"approve": True, "comment": "ok"})
    assert hr.get(f"/api/exit-cases/{cid}").json()["reason"]["evidence"]["ok"]


def test_notice_period_uses_longer_contract_notice(login, Session):
    with Session() as db:
        db.get(Employee, emp_id(db, "E2")).contract_notice_days = 60
        db.commit()
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    cid = hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]
    out = hr.post(f"/api/exit-cases/{cid}/dates", json={"notice_date": "2026-11-02", "pay_in_lieu": False}).json()
    assert out["notice_days"] == 60 and out["last_working_day"] == "2027-01-01"
    assert [t["rule"] for t in out["trace"]][:2] == ["IN-NOTICE-001", "IN-NOTICE-004"]


def test_hold_blocks_fnf(login, sent_case):
    legal, hr = login("legal"), login("hr")
    legal.post(f"/api/exit-cases/{sent_case}/hold", json={"text": "Investigation pending"})
    assert hr.post(f"/api/exit-cases/{sent_case}/fnf").status_code == 423
    legal.post(f"/api/exit-cases/{sent_case}/release-hold", json={"text": "Investigation closed"})
    assert hr.post(f"/api/exit-cases/{sent_case}/fnf").status_code == 201


def test_fnf_approval_separation_and_versions(login, sent_case, Session):
    fin, fin2, legal = login("finance"), login("finance2"), login("legal")
    st = fin.post(f"/api/exit-cases/{sent_case}/fnf").json()
    assert {ln["component"] for ln in st["lines"]} >= {"salary", "gratuity", "retrenchment_compensation", "notice_pay"}
    assert st["needs_legal"]
    fin.post(f"/api/fnf/{st['id']}/submit")
    r = fin.post(f"/api/fnf/{st['id']}/decision", json={"approve": True})
    assert r.status_code == 403  # preparer / computer can't approve
    assert fin2.post(f"/api/fnf/{st['id']}/decision", json={"approve": True}).json()["status"] == "submitted"
    assert legal.post(f"/api/fnf/{st['id']}/decision", json={"approve": True}).json()["status"] == "approved"
    with Session() as db:
        assert db.get(ExitCase, sent_case).state == "fnf_approved"
    v2 = fin.post(f"/api/exit-cases/{sent_case}/fnf").json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    assert fin.get(f"/api/fnf/{st['id']}").json()["status"] == "approved"  # stays until v2 is approved
    assert fin.post(f"/api/fnf/{st['id']}/mark-paid", json={"reference": "UTR123456"}).json()["status"] == "paid"
    assert "E2" in fin.get("/api/fnf/export/payroll.csv").text
    w = fin.get(f"/api/exit-cases/{sent_case}/fnf/what-if").json()
    assert set(w) == {"pay_in_lieu", "work_notice"}


def _approve_fnf(login, case_id):
    fin = login("finance")
    st = fin.post(f"/api/exit-cases/{case_id}/fnf").json()
    fin.post(f"/api/fnf/{st['id']}/submit")
    login("finance2").post(f"/api/fnf/{st['id']}/decision", json={"approve": True})
    login("legal").post(f"/api/fnf/{st['id']}/decision", json={"approve": True})


def test_documents_clearance_effective_close_and_hris(login, sent_case, Session, run_jobs, tmp_path):
    hr = login("hr")
    _approve_fnf(login, sent_case)
    r = hr.post(f"/api/exit-cases/{sent_case}/documents", json={"kind": "relieving_letter"})
    assert r.status_code == 409 and "Clearance" in r.json()["detail"]
    hr.post(f"/api/exit-cases/{sent_case}/clearance/exception")
    login("approver").post(f"/api/exit-cases/{sent_case}/clearance/exception/decision", json={"approve": True})
    doc = hr.post(f"/api/exit-cases/{sent_case}/documents",
                  json={"kind": "relieving_letter", "password_protect": True}).json()
    assert doc["password"] and doc["password_protected"]
    with Session() as db:
        d = db.get(Document, doc["id"])
        stored = storage_mod.load(d.storage_key)
        assert PdfReader(io.BytesIO(stored)).is_encrypted
        sealed = db.scalar(select(AuditLog).where(AuditLog.entity_type == "document", AuditLog.entity_id == d.id))
        assert sealed.after["sha256"] == d.sha256
        assert db.get(ExitCase, sent_case).state == "documents_issued"

    hr.post(f"/api/exit-cases/{sent_case}/mark-effective")
    with Session() as db:
        db.get(ExitCase, sent_case).owner = "abe@one.in"  # the approver now manages the case
        db.commit()
    r = login("approver").post(f"/api/exit-cases/{sent_case}/mark-effective/decision", json={"approve": True})
    assert r.status_code == 403
    assert login("approver2").post(f"/api/exit-cases/{sent_case}/mark-effective/decision",
                                   json={"approve": True}).json()["state"] == "effective"
    with Session() as db:
        assert db.get(Employee, emp_id(db, "E2")).status == "exited"

    assert hr.post(f"/api/exit-cases/{sent_case}/close").status_code == 409  # open tasks
    with Session() as db:
        for t in db.scalars(select(ExitTask).where(ExitTask.exit_case_id == sent_case, ExitTask.status == "open")):
            t.status = "done"
        db.commit()
    assert hr.post(f"/api/exit-cases/{sent_case}/close").json()["state"] == "closed"

    admin = login("admin")
    out = tmp_path / "outbox"
    admin.put("/api/integrations", json={"type": "hris", "provider": "csv_drop", "enabled": True,
                                         "config": {"inbox_path": str(tmp_path), "outbox_path": str(out)}})
    fin, fin2 = login("finance"), login("finance2")
    fin.post(f"/api/exit-cases/{sent_case}/push-hris")
    assert fin.post(f"/api/exit-cases/{sent_case}/push-hris/decision", json={"approve": True}).status_code == 403
    fin2.post(f"/api/exit-cases/{sent_case}/push-hris/decision", json={"approve": True})
    run_jobs()
    assert "E2,exited" in (out / "exits.csv").read_text()


def test_early_departure_creates_shortfall(login, Session, run_jobs):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    cid = hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]
    hr.post(f"/api/exit-cases/{cid}/reason", json={"reason_code": "RED-TEAM"})
    hr.post(f"/api/exit-cases/{cid}/dates", json={"notice_date": str(date.today()), "pay_in_lieu": False})
    approve_templates_and_wording(login, Session)
    d = hr.post(f"/api/plans/{pid}/notice-drafts", json={"template_id": template_id(hr, "termination_notice")}).json()
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": [x["id"] for x in d]}).json()
    hr.post(f"/api/notice-batches/{b['id']}/submit")
    login("approver").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True})
    hr.post(f"/api/notice-batches/{b['id']}/release")
    run_jobs()
    early = date.today() + timedelta(days=25)
    hr.post(f"/api/exit-cases/{cid}/last-day", json={"actual_last_day": str(early)})
    st = hr.post(f"/api/exit-cases/{cid}/fnf").json()
    short = next(ln for ln in st["lines"] if ln["component"] == "notice_shortfall")
    assert short["inputs"]["shortfall_days"] == 5


def test_exit_file_and_manager_view(login, sent_case):
    assert login("hr").get(f"/api/exit-cases/{sent_case}/file.pdf").content.startswith(b"%PDF")
    m = login("manager")
    assert [c["id"] for c in m.get("/api/exit-cases").json()] == [sent_case]  # E2 is in their team
    assert m.get(f"/api/exit-cases/{sent_case}").json()["fnf"] == []  # no pay data for managers


def test_storage_is_encrypted_at_rest(login, sent_case, Session):
    with Session() as db:
        d = db.scalar(select(Document).where(Document.exit_case_id == sent_case))
        raw = (Path(storage_mod.FILES_DIR) / d.storage_key).read_bytes()
        assert not raw.startswith(b"%PDF")
