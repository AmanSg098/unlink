import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import User
from tests.conftest import PASSWORD, SECRET, USERS, emp_id


def test_login_and_me(login):
    me = login("hr").get("/api/auth/me").json()
    assert (me["email"], me["role"], me["org_name"], me["mfa_required"]) == ("hal@one.in", "hr", "One", False)


def test_wrong_password_and_unknown_email_look_the_same(Session):
    c = TestClient(app)
    a = c.post("/api/auth/login", json={"email": "hal@one.in", "password": "nope"})
    b = c.post("/api/auth/login", json={"email": "nobody@one.in", "password": "nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_mfa_required_for_legal(Session):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": USERS["legal"][0], "password": PASSWORD})
    assert r.json()["mfa_required"] and r.json()["mfa_enrolled"]
    assert c.get("/api/plans").status_code == 401  # not verified yet
    assert c.post("/api/auth/mfa/verify", json={"code": "000000"}).status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"code": pyotp.TOTP(SECRET).now()}).status_code == 200
    assert c.get("/api/plans").status_code == 200


def test_mfa_enrolment(Session):
    with Session() as db:
        u = db.scalar(select(User).where(User.email == USERS["approver"][0]))
        u.mfa_secret_enc, u.mfa_enabled = None, False
        db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": USERS["approver"][0], "password": PASSWORD}).json()
    assert r["mfa_enrolled"] is False and r["otpauth_uri"].startswith("otpauth://") and "<svg" in r["qr_svg"]
    assert c.post("/api/auth/mfa/verify", json={"code": pyotp.TOTP(r["secret"]).now()}).status_code == 200
    with Session() as db:
        assert db.scalar(select(User).where(User.email == USERS["approver"][0])).mfa_enabled


def test_rate_limit_on_failed_logins(Session):
    c = TestClient(app)
    for _ in range(5):
        c.post("/api/auth/login", json={"email": "hal@one.in", "password": "wrong"})
    r = c.post("/api/auth/login", json={"email": "hal@one.in", "password": PASSWORD})
    assert r.status_code == 429


def test_dev_totp_helper(Session):
    r = TestClient(app).get("/api/dev/totp", params={"email": USERS["legal"][0]})
    assert r.status_code == 200 and r.json()["code"] == pyotp.TOTP(SECRET).now()


def test_role_enforcement(login):
    viewer, manager, hr = login("viewer"), login("manager"), login("hr")
    assert viewer.post("/api/plans", json={"name": "x", "target_count": 1, "weights": {"performance": 1}}).status_code == 403
    assert manager.get("/api/plans").status_code == 403
    assert hr.get("/api/users").status_code == 403
    assert hr.get("/api/audit").status_code == 403
    assert login("legal").get("/api/audit").status_code == 200


def test_manager_sees_only_own_team_and_masked_fields(login, Session):
    m = login("manager")
    codes = {e["employee_code"] for e in m.get("/api/employees").json()}
    assert "E2" in codes and "E6" not in codes and "M1" not in codes
    e2 = next(e for e in m.get("/api/employees").json() if e["employee_code"] == "E2")
    assert e2["annual_ctc_paise"] is None and e2["gender"] is None and "annual_ctc_paise" in e2["masked"]
    assert m.get(f"/api/employees/{emp_id(Session, 'E6')}").status_code == 404
    hr_view = next(e for e in login("hr").get("/api/employees").json() if e["employee_code"] == "E1")
    assert hr_view["annual_ctc_paise"] and hr_view["exclusion_reason"] == "On maternity leave"
    fin_view = next(e for e in login("finance").get("/api/employees").json() if e["employee_code"] == "E1")
    assert fin_view["annual_ctc_paise"] and fin_view["leave_status"] is None and fin_view["exclusion_reason"] == "Protected"


def test_org_isolation(login, Session):
    hr, other = login("hr"), login("other_org")
    pid = hr.post("/api/plans", json={"name": "x", "target_count": 1, "weights": {"performance": 1}}).json()["id"]
    assert other.get(f"/api/plans/{pid}").status_code == 404
    assert other.post(f"/api/plans/{pid}/run").status_code == 404
    assert other.get("/api/plans").json() == []
    assert [e["employee_code"] for e in other.get("/api/employees").json()] == ["X1"]
    assert other.get(f"/api/employees/{emp_id(Session, 'E2')}").status_code == 404
    assert all(a["actor"] != "hal@one.in" for a in other.get("/api/audit").json())


def test_deactivation_ends_sessions(login):
    admin, hr = login("admin"), login("hr")
    uid = hr.get("/api/auth/me").json()["id"]
    assert admin.patch(f"/api/users/{uid}", json={"active": False}).status_code == 200
    assert hr.get("/api/auth/me").status_code == 401
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 409


def test_request_id_header(login):
    r = login("hr").get("/api/auth/me", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
