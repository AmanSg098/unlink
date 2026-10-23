"""Usage:
  uv run python -m app.cli seed         load demo orgs, users, people, payroll, reviews, PIPs, rules, templates
  uv run python -m app.cli load-rules   load any new ruleset versions from rules/ into every org
  uv run python -m app.cli verify-audit check every org's audit hash chain
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app import audit
from app.auth import hash_password
from app.compliance.rules import load_all
from app.db import SessionLocal
from app.deps import Ctx
from app.importer import import_payroll, import_people
from app.models import (
    Checkin,
    Employee,
    Goal,
    Org,
    Pip,
    PipMilestone,
    Review,
    ReviewCycle,
    User,
)
from app.notices import load_templates

SEED_DIR = Path(__file__).resolve().parents[3] / "seed"
DEMO_PASSWORD = "unlink-demo"  # development only
ORGS = {
    "Demo Corp": {"legal_name": "Demo Corp Private Limited", "address": "Bengaluru, Karnataka",
                  "hr_contact_email": "hr@democorp.in", "test_addresses": ["hr-test@democorp.in"],
                  "establishment_size": 250, "escalation_days": 3},
    "Acme Pvt Ltd": {"legal_name": "Acme Private Limited", "hr_contact_email": "hr@acme.in",
                     "test_addresses": ["hr-test@acme.in"], "establishment_size": 40},
}
USERS = [  # org, email, name, role
    ("Demo Corp", "admin@democorp.in", "Asha Admin", "admin"),
    ("Demo Corp", "hr@democorp.in", "Harish HR", "hr"),
    ("Demo Corp", "manager@democorp.in", "Meera Manager", "manager"),
    ("Demo Corp", "legal@democorp.in", "Leena Legal", "legal"),
    ("Demo Corp", "finance@democorp.in", "Farhan Finance", "finance"),
    ("Demo Corp", "approver@democorp.in", "Anjali Approver", "approver"),
    ("Demo Corp", "viewer@democorp.in", "Vikram Viewer", "viewer"),
    ("Acme Pvt Ltd", "admin@acme.in", "Acme Admin", "admin"),
]
CYCLES = [("Q4 2025", date(2025, 10, 1), date(2025, 12, 31)), ("Q1 2026", date(2026, 1, 1), date(2026, 3, 31)),
          ("Q2 2026", date(2026, 4, 1), date(2026, 6, 30)), ("Q3 2026", date(2026, 7, 1), date(2026, 9, 30))]


def seed() -> None:
    with SessionLocal() as db:
        orgs = {}
        for name, settings in ORGS.items():
            org = db.scalar(select(Org).where(Org.name == name))
            if org is None:
                org = Org(name=name, settings=settings)
                db.add(org)
                db.flush()
            orgs[name] = org
        demo = orgs["Demo Corp"]
        sys_ctx = Ctx(org_id=demo.id, user_id=None, user="system:seed", role="admin")

        people_csv = (SEED_DIR / "employees.csv").read_text()
        res = import_people(db, sys_ctx, people_csv)
        pay = import_payroll(db, sys_ctx, (SEED_DIR / "payroll.csv").read_text())
        emps = {e.employee_code: e for e in db.scalars(select(Employee).where(Employee.org_id == demo.id))}

        # The demo manager runs the Support department (its head in the seed data).
        support_head = next(e.employee_code for e in emps.values() if e.department == "Support" and not e.manager_code)
        for org_name, email, name, role in USERS:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(org_id=orgs[org_name].id, email=email, full_name=name, role=role,
                            password_hash=hash_password(DEMO_PASSWORD),
                            employee_code=support_head if role == "manager" else None))

        cycles = {}
        for name, start, end in CYCLES:
            c = db.scalar(select(ReviewCycle).where(ReviewCycle.org_id == demo.id, ReviewCycle.name == name))
            if c is None:
                c = ReviewCycle(org_id=demo.id, name=name, period_start=start, period_end=end, status="closed",
                                created_by="system:seed")
                db.add(c)
                db.flush()
            cycles[name] = c
        if not db.scalar(select(Review.id).where(Review.org_id == demo.id).limit(1)):
            with (SEED_DIR / "reviews.csv").open() as f:
                for r in csv.DictReader(f):
                    e = emps[r["employee_code"]]
                    db.add(Review(org_id=demo.id, cycle_id=cycles[r["cycle"]].id, employee_id=e.id,
                                  self_rating=float(r["self_rating"]), manager_rating=float(r["manager_rating"]),
                                  calibrated_rating=float(r["calibrated_rating"]),
                                  manager_comment=r["manager_comment"] or None, calibrated_by="system:seed"))
        _seed_performance(db, demo.id, emps)
        for org in orgs.values():
            load_all(db, org.id)
            load_templates(db, org.id)
        audit.record_raw(db, demo.id, "system:seed", "org", demo.id, "seed", None,
                         {"people_created": res["created"], "payroll_rows": pay["created"] + pay["updated"]})
        db.commit()
    print(f"Seeded Demo Corp: {res['created']} people created, {res['updated']} updated, "
          f"{len(res['errors'])} errors; payroll {pay['created'] + pay['updated']} rows")
    print(f"Demo logins (password '{DEMO_PASSWORD}'): " + ", ".join(f"{e} ({r})" for _, e, _, r in USERS))
    print("Legal, Finance, Approver and Admin also need a TOTP code (dev helper: /api/dev/totp?email=...).")


def _seed_performance(db, org_id: int, emps: dict[str, Employee]) -> None:
    if db.scalar(select(Pip.id).where(Pip.org_id == org_id).limit(1)):
        return
    rng = random.Random(5)
    today = date(2026, 10, 1)
    low = sorted((e for e in emps.values() if e.performance_rating <= 2.3 and e.leave_status == "none"
                  and not e.protected_flag), key=lambda e: (e.performance_rating, e.employee_code))
    plan = (["active"] * 4) + (["not_met"] * 3) + (["met"] * 2) + ["proposed"]
    for e, kind in zip(low, plan):
        if kind == "active":
            start = today - timedelta(days=20)
            p = Pip(org_id=org_id, employee_id=e.id, reason_category="performance", status="active",
                    gaps="Quarterly targets missed for two consecutive cycles; quality issues in recent work.",
                    success_criteria="Meet 90% of agreed weekly targets for six weeks; no repeat quality escalations.",
                    support="Weekly coaching with the team lead; refresher training.", start_date=start,
                    end_date=start + timedelta(days=60), proposed_by="hr@democorp.in", activated_by="hr@democorp.in",
                    employee_ack="acknowledged")
            db.add(p)
            db.flush()
            db.add(PipMilestone(org_id=org_id, pip_id=p.id, on_date=start + timedelta(days=14),
                                evidence_reviewed="Weekly target sheet and QA reviews", outcome="partially_met",
                                manager_signed_by="manager@democorp.in", employee_ack="acknowledged"))
        elif kind in ("not_met", "met"):
            start = today - timedelta(days=150)
            p = Pip(org_id=org_id, employee_id=e.id, reason_category="performance", status="closed", outcome=kind,
                    gaps="Targets missed and deadlines slipped over the review period.",
                    success_criteria="Meet agreed targets for eight consecutive weeks.",
                    support="Fortnightly coaching; reduced on-call load.", start_date=start,
                    end_date=start + timedelta(days=60), proposed_by="hr@democorp.in",
                    activated_by="hr@democorp.in", closed_by="hr@democorp.in",
                    final_review="Final review held with the employee; evidence reviewed: target sheets, QA reports.",
                    final_review_on=start + timedelta(days=60), employee_ack="acknowledged")
            db.add(p)
            db.flush()
            for wk, outcome in ((3, "not_met" if kind == "not_met" else "partially_met"), (6, kind)):
                db.add(PipMilestone(org_id=org_id, pip_id=p.id, on_date=start + timedelta(weeks=wk),
                                    evidence_reviewed="Target sheet and QA reports", outcome=outcome,
                                    manager_signed_by="manager@democorp.in", employee_ack="acknowledged"))
        else:
            db.add(Pip(org_id=org_id, employee_id=e.id, reason_category="performance", status="proposed",
                       gaps="Response times consistently above the team standard.",
                       success_criteria="Median first response under 4 hours for six weeks.",
                       start_date=today + timedelta(days=7), end_date=today + timedelta(days=67),
                       proposed_by="manager@democorp.in"))
    for e in rng.sample(sorted(emps.values(), key=lambda e: e.employee_code), 40):
        for title in ("Deliver quarterly objectives", "Complete one certification"):
            db.add(Goal(org_id=org_id, employee_id=e.id, title=title, target="100%", weight=1,
                        due_date=date(2026, 12, 31), progress_pct=rng.choice([10, 25, 40, 60, 80]),
                        created_by="hr@democorp.in"))
    for e in [e for e in emps.values() if e.department == "Support"][:20]:
        db.add(Checkin(org_id=org_id, employee_id=e.id, scheduled_for=date(2026, 9, 15), held_on=date(2026, 9, 15),
                       summary="Discussed priorities and workload for the next sprint.",
                       sentiment=rng.choice(["positive", "neutral", "neutral", "concern"]),
                       created_by="manager@democorp.in"))


def load_rules() -> None:
    with SessionLocal() as db:
        for org in db.scalars(select(Org)):
            loaded = load_all(db, org.id)
            print(f"{org.name}: {', '.join(f'{r.key} {r.version}' for r in loaded)}")
        db.commit()


def verify_audit() -> None:
    with SessionLocal() as db:
        for org in db.scalars(select(Org)):
            print(org.name, audit.verify_chain(db, org.id))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"seed": seed, "load-rules": load_rules, "verify-audit": verify_audit}.get(cmd, lambda: print(__doc__))()
