"""Shared test harness: in-memory DB, demo org data, signed-in clients (with real TOTP for MFA roles),
encrypted file storage in a temp dir, captured mail, and a fake PDF renderer (no pango needed)."""

import io
import re
from datetime import date

import pyotp
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.documents as documents_mod
import app.reports as reports_mod
import app.storage as storage_mod
from app.auth import hash_password
from app.compliance.rules import load_all
from app.crypto import encrypt_str
from app.db import get_db
from app.main import app
from app.models import Base, CapturedMail, Employee, Org, PayrollInput, User
from app.notices import load_templates
from app.worker import drain

PASSWORD = "test-password-123"
SECRET = "JBSWY3DPEHPK3PXP"  # TOTP secret for MFA roles in tests
# key: (email, org, role, employee_code)
USERS = {
    "admin": ("ada@one.in", 1, "admin", None),
    "hr": ("hal@one.in", 1, "hr", None),
    "hr2": ("hana@one.in", 1, "hr", None),
    "manager": ("mo@one.in", 1, "manager", "M1"),
    "legal": ("lee@one.in", 1, "legal", None),
    "legal2": ("lou@one.in", 1, "legal", None),
    "finance": ("fay@one.in", 1, "finance", None),
    "finance2": ("fin@one.in", 1, "finance", None),
    "approver": ("abe@one.in", 1, "approver", None),
    "approver2": ("amy@one.in", 1, "approver", None),
    "viewer": ("vic@one.in", 1, "viewer", None),
    "other_org": ("mallory@two.in", 2, "admin", None),
}
MFA = {"admin", "legal", "finance", "approver"}
RUPEE = 100


def emp(code, perf, org_id=1, **kw):
    base = dict(org_id=org_id, employee_code=code, full_name=f"Person {code}", email=f"{code.lower()}@one.in",
                personal_email=f"p.{code.lower()}@example.com", department="Eng", role="Engineer", location="Pune",
                manager_code="M1", hire_date=date(2018, 1, 15), employment_type="permanent", contract_notice_days=30,
                annual_ctc_paise=1_200_000 * RUPEE, salary_breakup={}, performance_rating=perf, potential_rating=3,
                critical_skill_score=3, gender="Female", age_band="30-39", leave_status="none", protected_flag=False,
                custom_metrics={})
    base.update(kw)
    return Employee(**base)


def fake_pdf(_html: str) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture
def Session(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_mod, "FILES_DIR", tmp_path / "files")
    monkeypatch.setattr(documents_mod, "html_to_pdf", fake_pdf)
    monkeypatch.setattr(reports_mod, "html_to_pdf", fake_pdf)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    pw = hash_password(PASSWORD)
    with Session() as db:
        db.add_all([Org(id=1, name="One", settings={"legal_name": "One Pvt Ltd", "hr_contact_email": "hr@one.in",
                                                    "test_addresses": ["hr-test@one.in"], "establishment_size": 50}),
                    Org(id=2, name="Two", settings={"hr_contact_email": "hr@two.in", "test_addresses": ["t@two.in"]})])
        for key, (email, org, role, code) in USERS.items():
            db.add(User(org_id=org, email=email, full_name=key.title(), role=role, password_hash=pw, employee_code=code,
                        mfa_secret_enc=encrypt_str(SECRET) if role in MFA else None, mfa_enabled=role in MFA))
        db.add_all([
            emp("M1", 4.0, manager_code=None, role="Engineering Lead", hire_date=date(2015, 6, 1)),
            emp("E1", 1.0, leave_status="maternity"),  # worst performer but hard-excluded
            emp("E2", 2.0, gender="Male"),
            emp("E3", 3.0, hire_date=date(2024, 3, 1)),
            emp("E4", 4.0, gender="Male"),
            emp("E5", 1.5, protected_flag=True),
            emp("E6", 2.5, manager_code="Z9", department="Sales", role="Account Executive"),
            emp("X1", 1.0, org_id=2, manager_code=None),
        ])
        db.flush()
        for code in ("E2", "E3", "E4", "E6"):
            e = db.scalar(select(Employee).where(Employee.employee_code == code, Employee.org_id == 1))
            db.add(PayrollInput(org_id=1, employee_id=e.id, period="2026-10", updated_by="seed", data={
                "basic": 40_000 * RUPEE, "da": 0, "hra": 20_000 * RUPEE, "special": 40_000 * RUPEE,
                "leave_encashable_days": 10, "tds": 8_000 * RUPEE}))
            e.salary_breakup = {"basic": 40_000 * RUPEE, "da": 0, "hra": 20_000 * RUPEE, "special": 40_000 * RUPEE}
        for org_id in (1, 2):
            load_all(db, org_id)
            load_templates(db, org_id)
        db.commit()

    def _db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    yield Session
    app.dependency_overrides.clear()


@pytest.fixture
def login(Session):
    """login("hr") -> a TestClient signed in as that user, MFA completed where required."""

    def _login(who: str) -> TestClient:
        email = USERS[who][0]
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        if r.json().get("mfa_required"):
            v = c.post("/api/auth/mfa/verify", json={"code": pyotp.TOTP(SECRET).now()})
            assert v.status_code == 200, v.text
        return c

    return _login


@pytest.fixture
def run_jobs(Session):
    def _run():
        with Session() as db:
            drain(db)

    return _run


@pytest.fixture
def mails(Session):
    def _get():
        with Session() as db:
            return [{"to": m.to, "subject": m.subject, "text": m.text, "attachments": m.attachments}
                    for m in db.scalars(select(CapturedMail).order_by(CapturedMail.id))]

    return _get


def emp_id(src, code: str, org_id: int = 1) -> int:
    """Employee id by code. Pass an open session (`db`) inside `with Session() as db:` blocks: the test DB shares
    one connection, so opening a second session there would roll back the first one's transaction."""
    q = select(Employee.id).where(Employee.employee_code == code, Employee.org_id == org_id)
    if isinstance(src, OrmSession):
        return src.scalar(q)
    with src() as db:
        return db.scalar(q)


def make_plan(c, **kw) -> int:
    body = {"name": "Q4", "target_count": 1, "weights": {"performance": 1}, **kw}
    r = c.post("/api/plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def results(c, pid) -> dict:
    return {r["employee_code"]: r for r in c.get(f"/api/plans/{pid}/results").json()["rows"]}


def approve_plan(login, hr, pid, justification="Reviewed; flags explained by small team size"):
    """Submit as HR and approve through Legal → Finance → Approver."""
    assert hr.post(f"/api/plans/{pid}/submit").status_code == 200
    for who in ("legal", "finance", "approver"):
        r = login(who).post(f"/api/plans/{pid}/decision",
                            json={"approve": True, "comment": "ok", "fairness_justification": justification})
        assert r.status_code == 200, r.text
    return pid


def approve_templates_and_wording(login, Session, codes=("RED-TEAM",)):
    legal = login("legal")
    for t in legal.get("/api/notice-templates").json():
        if t["status"] == "draft":
            assert legal.post(f"/api/notice-templates/{t['id']}/approve").status_code == 200
    for code in codes:
        assert legal.post(f"/api/reasons/{code}/approve-wording").status_code == 200
    return legal


def template_id(c, key: str) -> int:
    return next(t["id"] for t in c.get("/api/notice-templates").json() if t["key"] == key and t["status"] != "retired")


def ack_token(text: str) -> str:
    return re.search(r"/ack/([\w-]+)", text).group(1)
