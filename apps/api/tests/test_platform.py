"""Audit chain, append-only enforcement, integrations, retention, data subject export, real PDF rendering."""

import os
import sqlite3
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text

import app.integrations.jobs as int_jobs
from app.audit import record_raw, verify_chain
from app.deps import Ctx
from app.models import AuditLog, ClearanceItem, Employee, EmployeeHistory, ExitCase, QueueJob, utcnow
from app.retention import retention_sweep
from app.worker import drain
from tests.conftest import approve_plan, emp_id, make_plan


def test_audit_chain_verifies_and_detects_tampering(login, Session):
    hr = login("hr")
    pid = make_plan(hr)
    hr.post(f"/api/plans/{pid}/run")
    assert login("legal").get("/api/audit/verify").json()["ok"]
    # The in-memory test DB has no triggers, so a raw UPDATE simulates tampering at the storage level.
    with Session() as db:
        target = db.scalars(select(AuditLog).where(AuditLog.org_id == 1).order_by(AuditLog.id)).all()[1]
        db.execute(text("UPDATE audit_log SET action = 'edited' WHERE id = :id"), {"id": target.id})
        db.commit()
        db.expire_all()  # re-read rows from the database, not the session cache
        result = verify_chain(db, 1)
    assert not result["ok"] and result["first_bad_id"] == target.id


def test_audit_log_append_only_orm(Session):
    with Session() as db:
        record_raw(db, 1, "tester", "x", None, "y")
        db.commit()
        e = db.scalar(select(AuditLog))
        e.action = "tampered"
        with pytest.raises(RuntimeError):
            db.commit()


def test_audit_log_append_only_db_trigger(tmp_path: Path):
    db_file = tmp_path / "t.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}"}
    subprocess.run(["alembic", "upgrade", "head"], cwd=Path(__file__).parents[1], env=env, check=True,
                   capture_output=True)
    con = sqlite3.connect(db_file)
    con.execute("INSERT INTO orgs (id, name, region, timezone, settings) VALUES (1, 'o', 'IN', 'UTC', '{}')")
    con.execute("INSERT INTO audit_log (org_id, actor, created_at, entity_type, action, prev_hash, hash) "
                "VALUES (1, 'a', '2026-01-01', 'x', 'y', '0', '1')")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("UPDATE audit_log SET action='z'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("DELETE FROM audit_log")


def test_audit_export_json(login):
    r = login("legal").get("/api/audit/export.json")
    assert r.status_code == 200 and r.json()["verification"]["ok"]


def test_unimplemented_integration_cannot_be_enabled(login):
    r = login("admin").put("/api/integrations", json={"type": "hris", "provider": "keka", "enabled": True})
    assert r.status_code == 422 and "not implemented" in r.json()["detail"]


def test_ticket_webhook_on_access_revocation(login, Session, monkeypatch):
    calls = []
    monkeypatch.setattr(int_jobs, "post_json", lambda url, payload, token=None: calls.append((url, payload, token)) or 201)
    admin = login("admin")
    admin.put("/api/integrations", json={"type": "ticketing", "provider": "webhook", "enabled": True,
                                         "config": {"url": "https://tickets.example.com/hook"},
                                         "secrets": {"token": "s3cret"}})
    listed = admin.get("/api/integrations").json()["integrations"][0]
    assert listed["secret_keys"] == ["token"] and "s3cret" not in str(listed)
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]})
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    cid = hr.post("/api/exit-cases", json={"plan_id": pid}).json()[0]["id"]
    with Session() as db:
        db.add(ClearanceItem(org_id=1, exit_case_id=cid, category="access", key="access_vpn", label="VPN",
                             owner_role="hr"))
        db.commit()
        item = db.scalar(select(ClearanceItem).where(ClearanceItem.exit_case_id == cid)).id
    hr.patch(f"/api/exit-cases/{cid}/clearance/{item}", json={"status": "requested"})
    with Session() as db:
        drain(db)
        assert db.get(ClearanceItem, item).ticket_ref == "webhook:201"
    assert calls[0][1]["employee_code"] == "E2" and calls[0][2] == "s3cret"


def test_hris_sync_shows_conflicts_for_review(login, Session, tmp_path, run_jobs):
    (tmp_path / "people.csv").write_text(
        "employee_code,full_name,department,role,location,hire_date,annual_ctc,performance_rating,"
        "potential_rating,critical_skill_score,gender,age_band\n"
        "E2,Person E2,Eng,Senior Engineer,Pune,2018-01-15,1200000,2.0,3,3,Male,30-39\n")
    admin = login("admin")
    admin.put("/api/integrations", json={"type": "hris", "provider": "csv_drop", "enabled": True,
                                         "config": {"inbox_path": str(tmp_path), "outbox_path": str(tmp_path / "out")}})
    run = admin.post("/api/integrations/hris/sync").json()
    run_jobs()
    run = next(r for r in admin.get("/api/integrations").json()["runs"] if r["id"] == run["id"])
    assert run["status"] == "needs_review"
    assert {"employee_code": "E2", "field": "role", "current": "Engineer", "incoming": "Senior Engineer"} in run["summary"]["conflicts"]
    with Session() as db:
        assert db.get(Employee, emp_id(db, "E2")).role == "Engineer"  # nothing overwritten yet
    assert admin.post(f"/api/integrations/runs/{run['id']}/apply", json=["E2"]).json()["applied"] == ["E2"]
    with Session() as db:
        assert db.get(Employee, emp_id(db, "E2")).role == "Senior Engineer"
        assert db.scalar(select(EmployeeHistory).where(EmployeeHistory.field == "role"))


def test_retention_pseudonymises_old_closed_cases_but_respects_legal_hold(login, Session):
    hr = login("hr")
    pid = make_plan(hr, filters={"departments": ["Eng"]}, target_count=2)
    hr.post(f"/api/plans/{pid}/run")
    approve_plan(login, hr, pid)
    cases = hr.post("/api/exit-cases", json={"plan_id": pid}).json()
    e2_id, e3_id = emp_id(Session, "E2"), emp_id(Session, "E3")  # look up before opening the session
    with Session() as db:
        for c in cases:
            case = db.get(ExitCase, c["id"])
            case.state, case.closed_at = "closed", utcnow() - timedelta(days=4 * 365)
        db.get(Employee, e3_id).legal_hold = True
        db.commit()
        retention_sweep(db, QueueJob(org_id=1, kind="retention_sweep", payload={}))
        db.commit()
        e2, e3 = db.get(Employee, e2_id), db.get(Employee, e3_id)
        assert e2.full_name == "Former employee E2" and e2.email is None and e2.pseudonymised_at
        assert e3.full_name == "Person E3"


def test_data_subject_export(login, Session):
    r = login("legal").get(f"/api/employees/{emp_id(Session, 'E2')}/export")
    assert r.status_code == 200 and r.json()["employee"]["employee_code"] == "E2"
    assert any(a["action"] == "data_export" for a in login("legal").get("/api/audit").json())


def test_real_weasyprint_pdf(Session):
    weasyprint = pytest.importorskip("weasyprint", exc_type=OSError)
    pdf = weasyprint.HTML(string="<h1>Unlink</h1>").write_pdf()
    assert pdf.startswith(b"%PDF")


def test_admin_context_passes_every_role_check():
    assert Ctx(org_id=1, user_id=None, user="system", role="admin").has("hr", "legal")


def test_worker_process_registers_handlers(tmp_path):
    """`python -m app.worker` must see the handlers (it runs as __main__, separate from app.worker)."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}"}
    out = subprocess.run([sys.executable, "-m", "app.worker", "--check"], capture_output=True, text=True, env=env,
                         cwd=Path(__file__).resolve().parents[1], timeout=60)
    assert out.returncode == 0, out.stderr
    for kind in ("send_message", "staff_email", "ticket_create", "retention_sweep", "weekly_report"):
        assert kind in out.stderr
