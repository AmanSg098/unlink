from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.notices.sending as sending
from app.compliance.rules import RuleBook
from app.main import app
from app.models import Employee, ExitCase, ExitTask, NoticeMessage, Notification, QueueJob
from tests.conftest import (
    ack_token,
    approve_plan,
    approve_templates_and_wording,
    emp_id,
    make_plan,
    template_id,
)


@pytest.fixture
def cases(login, Session):
    """An approved plan selecting E2 and E3, with exit cases ready for notices (reason + dates set)."""
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]}, target_count=2)
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    created = hr.post("/api/exit-cases", json={"plan_id": pid}).json()
    assert {c["employee"]["employee_code"] for c in created} == {"E2", "E3"}
    for c in created:
        assert hr.post(f"/api/exit-cases/{c['id']}/reason", json={"reason_code": "RED-TEAM"}).status_code == 200
        r = hr.post(f"/api/exit-cases/{c['id']}/dates", json={"notice_date": str(date.today()), "pay_in_lieu": False})
        assert r.status_code == 200, r.text
    return pid, {c["employee"]["employee_code"]: c["id"] for c in created}


def _drafts(hr, pid, tid):
    r = hr.post(f"/api/plans/{pid}/notice-drafts", json={"template_id": tid})
    assert r.status_code == 201, r.text
    return [d["id"] for d in r.json()]


def test_unapproved_template_and_wording_block_submission(login, cases):
    pid, _ = cases
    hr = login("hr")
    drafts = _drafts(hr, pid, template_id(hr, "termination_notice"))
    b = hr.post("/api/notice-batches", json={"name": "Wave 1", "draft_ids": drafts}).json()
    r = hr.post(f"/api/notice-batches/{b['id']}/submit")
    assert r.status_code == 422 and "isn't legal-approved" in r.json()["detail"]
    assert "wording" in r.json()["detail"]  # reason wording not yet approved by Legal


def test_missing_merge_fields_are_listed(login, cases, Session):
    pid, ids = cases
    with Session() as db:
        db.get(ExitCase, ids["E2"]).notice_date = None
        db.commit()
    approve_templates_and_wording(login, Session)
    hr = login("hr")
    d = hr.post(f"/api/plans/{pid}/notice-drafts", json={"template_id": template_id(hr, "termination_notice"),
                                                           "case_ids": [ids["E2"]]}).json()[0]
    assert any(m.startswith("notice_date") for m in d["missing_fields"])


def test_full_notice_flow(login, cases, Session, run_jobs, mails):
    pid, ids = cases
    approve_templates_and_wording(login, Session)
    hr = login("hr")
    drafts = _drafts(hr, pid, template_id(hr, "termination_notice"))
    b = hr.post("/api/notice-batches", json={"name": "Wave 1", "draft_ids": drafts}).json()
    assert hr.post(f"/api/notice-batches/{b['id']}/submit").json()["status"] == "pending_approval"

    # The drafter can't approve sending; an approver can.
    assert login("hr2").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True}).status_code == 403
    r = login("approver").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True, "comment": "ok"})
    assert r.json()["status"] == "approved"

    # Test send goes only to internal addresses and is marked TEST.
    hr.post(f"/api/notice-batches/{b['id']}/test-send")
    run_jobs()
    sent = [m for m in mails() if not m["subject"].startswith("Unlink:")]  # skip staff notifications
    assert sent and all(m["to"] == ["hr-test@one.in"] and m["subject"].startswith("[TEST]") for m in sent)

    assert hr.post(f"/api/notice-batches/{b['id']}/release").json()["queued"] == 2
    run_jobs()
    real = [m for m in mails() if not m["subject"].startswith(("[TEST]", "Unlink:"))]
    notices = [m for m in real if m["subject"] == "Notice of termination of employment"]
    passwords = [m for m in real if m["subject"].startswith("Password for:")]
    assert len(notices) == 2 and len(passwords) == 2
    e2_mail = next(m for m in notices if "e2@one.in" in m["to"])
    assert "p.e2@example.com" in e2_mail["to"]  # termination template also goes to personal email
    assert e2_mail["attachments"] and "Password" not in e2_mail["text"]

    with Session() as db:
        case = db.get(ExitCase, ids["E2"])
        assert case.state == "notice_period" and case.notice_days == 30
        assert db.get(Employee, emp_id(db, "E2")).status == "on_notice"
        msg = db.scalar(select(NoticeMessage).where(NoticeMessage.exit_case_id == case.id,
                                                    NoticeMessage.is_test.is_(False)))
        assert msg.status == "delivered"

    # Acknowledgement by link records time and IP.
    token = ack_token(e2_mail["text"])
    public = TestClient(app)
    assert public.get(f"/api/acknowledge/{token}").json()["acknowledged_at"] is None
    assert public.post(f"/api/acknowledge/{token}").status_code == 200
    detail = hr.get(f"/api/exit-cases/{ids['E2']}").json()
    assert detail["messages"][0]["acknowledged_at"]


def test_edit_after_approval_requires_new_approval(login, cases, Session):
    pid, _ = cases
    approve_templates_and_wording(login, Session)
    hr = login("hr")
    drafts = _drafts(hr, pid, template_id(hr, "termination_notice"))
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": drafts}).json()
    hr.post(f"/api/notice-batches/{b['id']}/submit")
    login("legal").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True})
    d = hr.get(f"/api/notice-drafts/{drafts[0]}").json()
    assert hr.patch(f"/api/notice-drafts/{drafts[0]}", json={"subject": d["subject"],
                                                              "body": d["body"] + "\nA small edit."}).status_code == 200
    r = hr.post(f"/api/notice-batches/{b['id']}/release")
    assert r.status_code == 409


def test_protected_terms_block(login, cases, Session):
    pid, _ = cases
    approve_templates_and_wording(login, Session)
    hr = login("hr")
    drafts = _drafts(hr, pid, template_id(hr, "termination_notice"))
    d = hr.get(f"/api/notice-drafts/{drafts[0]}").json()
    nd = hr.patch(f"/api/notice-drafts/{drafts[0]}", json={"subject": d["subject"],
                                                            "body": d["body"] + "\nGiven your pregnancy..."}).json()
    assert "pregnancy" in nd["flagged_terms"]
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": [nd["id"], drafts[1]]}).json()
    r = hr.post(f"/api/notice-batches/{b['id']}/submit")
    assert r.status_code == 422 and "protected terms" in r.json()["detail"]


def test_throttle_bounce_and_withdrawal(login, cases, Session, run_jobs, monkeypatch):
    pid, ids = cases
    approve_templates_and_wording(login, Session)
    with Session() as db:
        e3 = db.get(Employee, emp_id(db, "E3"))
        e3.email, e3.personal_email = "e3@bounce.invalid", None
        db.commit()
    hr = login("hr")
    drafts = _drafts(hr, pid, template_id(hr, "termination_notice"))
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": drafts}).json()
    hr.post(f"/api/notice-batches/{b['id']}/submit")
    login("approver").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True})
    monkeypatch.setattr(sending, "MAIL_RATE_PER_MINUTE", 1)
    hr.post(f"/api/notice-batches/{b['id']}/release")
    run_jobs()
    with Session() as db:
        statuses = sorted(m.status for m in db.scalars(select(NoticeMessage).where(NoticeMessage.is_test.is_(False))))
        # One went out; the other waits for the next minute (throttled, not failed).
        assert statuses.count("queued") == 1
        assert db.scalar(select(QueueJob).where(QueueJob.kind == "send_message", QueueJob.status == "queued"))
    monkeypatch.setattr(sending, "MAIL_RATE_PER_MINUTE", 100)
    with Session() as db:
        for j in db.scalars(select(QueueJob).where(QueueJob.status == "queued")):
            j.run_after = j.created_at
        db.commit()
    run_jobs()
    with Session() as db:
        bounced = db.scalar(select(NoticeMessage).where(NoticeMessage.exit_case_id == ids["E3"],
                                                        NoticeMessage.is_test.is_(False)))
        assert bounced.status == "bounced"
        assert db.scalar(select(ExitTask).where(ExitTask.exit_case_id == ids["E3"], ExitTask.auto_key == "resolve_contact"))
        assert db.scalar(select(Notification).where(Notification.kind == "bounce"))
    r = hr.post(f"/api/exit-cases/{ids['E3']}/withdraw", json={"text": "Role retained after review"})
    assert r.json()["state"] == "withdrawn"


def test_consultation_required_for_large_groups(login, cases, Session, monkeypatch):
    pid, _ = cases
    approve_templates_and_wording(login, Session)
    original = RuleBook.value

    def value(self, key, default=None):
        if key == "IN-CONSULT-001":
            return {"min_group_size": 2, "days_before_notice": 7}
        return original(self, key, default)

    monkeypatch.setattr(RuleBook, "value", value)
    hr = login("hr")
    b = hr.post("/api/notice-batches", json={"name": "W", "draft_ids": _drafts(hr, pid, template_id(hr, "termination_notice"))}).json()
    hr.post(f"/api/notice-batches/{b['id']}/submit")
    login("approver").post(f"/api/notice-batches/{b['id']}/approve", json={"approve": True})
    r = hr.post(f"/api/notice-batches/{b['id']}/release")
    assert r.status_code == 409 and "consultation" in r.json()["detail"]
