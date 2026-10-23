"""Generate synthetic demo data (no real people). Deterministic: the same files every run.

Writes seed/employees.csv, seed/payroll.csv and seed/reviews.csv.
Usage: python3 seed/generate.py [count]
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Arjun", "Rohan", "Kabir", "Dev", "Nikhil", "Rahul",
         "Ananya", "Diya", "Isha", "Kavya", "Meera", "Priya", "Riya", "Saanvi", "Tara", "Neha",
         "Sam", "Alex", "Jordan", "Noor", "Zara", "Farhan", "Imran", "Joseph", "Maria", "Anita"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Gupta", "Mehta", "Patel", "Singh", "Das",
        "Rao", "Kulkarni", "Menon", "Chopra", "Bose", "Khan", "DSouza", "Pillai", "Joshi", "Shetty"]
DEPTS = {
    "Engineering": (["Software Engineer", "Senior Engineer", "Staff Engineer", "QA Engineer"], 1_800_000),
    "Sales": (["Account Executive", "Sales Manager", "SDR"], 1_200_000),
    "Support": (["Support Specialist", "Support Lead"], 700_000),
    "Marketing": (["Marketing Associate", "Content Lead", "Growth Manager"], 1_000_000),
    "Finance": (["Analyst", "Accountant", "Finance Manager"], 1_100_000),
    "Operations": (["Ops Associate", "Ops Manager"], 800_000),
    "HR": (["HR Generalist", "Recruiter"], 750_000),
}
DEPT_WEIGHTS = [35, 18, 15, 10, 8, 9, 5]
LOCATIONS = ["Bengaluru", "Mumbai", "Pune", "Hyderabad", "Delhi"]
GENDERS = ["Female", "Male", "Non-binary"]
AGE_BANDS = ["<30", "30-39", "40-49", "50+"]
AS_OF = date(2026, 10, 1)
CYCLES = [("Q4 2025", date(2025, 10, 1), date(2025, 12, 31)), ("Q1 2026", date(2026, 1, 1), date(2026, 3, 31)),
          ("Q2 2026", date(2026, 4, 1), date(2026, 6, 30)), ("Q3 2026", date(2026, 7, 1), date(2026, 9, 30))]
SENIOR = ("Senior", "Staff", "Manager", "Lead")


def clamp(x: float, lo: float = 1, hi: float = 5) -> float:
    return round(min(hi, max(lo, x)), 1)


def generate(n: int) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(42)
    metrics_rng = random.Random(7)
    extra_rng = random.Random(11)  # separate streams keep earlier columns stable when new ones are added
    rows = []
    for i in range(1, n + 1):
        dept = rng.choices(list(DEPTS), weights=DEPT_WEIGHTS)[0]
        roles, base = DEPTS[dept]
        role = rng.choice(roles)
        senior = any(w in role for w in SENIOR)
        age_band = rng.choices(AGE_BANDS, weights=[30, 40, 20, 10])[0]
        max_years = {"<30": 6, "30-39": 14, "40-49": 22, "50+": 30}[age_band]
        tenure_days = rng.randint(60, max_years * 365)
        leave_roll = rng.random()
        leave = "maternity" if leave_roll < 0.03 else "medical" if leave_roll < 0.06 else \
            "other" if leave_roll < 0.09 else "none"
        first, last = rng.choice(FIRST), rng.choice(LAST)
        code = f"E{i:04d}"
        hire = AS_OF - timedelta(days=tenure_days)
        ctc = round(base * (1.6 if senior else 1.0) * rng.uniform(0.75, 1.35), -3)
        perf = clamp(rng.gauss(3.3, 0.8))
        etype = extra_rng.choices(["permanent", "fixed_term", "contract", "intern"], weights=[88, 6, 4, 2])[0]
        rows.append({
            "employee_code": code, "full_name": f"{first} {last}", "department": dept, "role": role,
            "location": rng.choice(LOCATIONS), "hire_date": hire.isoformat(), "annual_ctc": int(ctc),
            "performance_rating": perf,
            "potential_rating": clamp(rng.gauss(3.2, 0.9)),
            "critical_skill_score": clamp(rng.gauss(3.0 + (0.6 if senior else 0), 0.9)),
            "gender": rng.choices(GENDERS, weights=[42, 55, 3])[0], "age_band": age_band,
            "leave_status": leave, "protected_flag": "true" if rng.random() < 0.04 else "false",
            "kpi_engagement_score": clamp(metrics_rng.gauss(3.4, 0.7)),
            "kpi_quota_attainment": round(metrics_rng.uniform(0.55, 1.35), 2) if dept == "Sales" else "",
            "email": f"{first}.{last}.{code}@democorp.in".lower(),
            "personal_email": f"{first}.{code}@example.com".lower(),
            "employment_type": etype,
            "confirmation_date": (hire + timedelta(days=180)).isoformat() if etype == "permanent" else "",
            "contract_end_date": (AS_OF + timedelta(days=extra_rng.randint(30, 300))).isoformat()
            if etype in ("fixed_term", "contract") else "",
            "contract_notice_days": 60 if senior else (30 if etype == "permanent" else 15),
            "manager_code": "",
            "_senior": senior,
        })
    # Reporting lines: the first senior person in each department heads it; other seniors report to the head,
    # everyone else to a senior in their department.
    by_dept: dict[str, list[dict]] = {}
    for r in rows:
        by_dept.setdefault(r["department"], []).append(r)
    for dept, members in by_dept.items():
        seniors = [r for r in members if r["_senior"]] or members[:1]
        head = seniors[0]
        for r in members:
            if r is head:
                continue
            r["manager_code"] = head["employee_code"] if r["_senior"] else extra_rng.choice(seniors)["employee_code"]
    for r in rows:
        del r["_senior"]

    payroll = []
    for r in rows:
        monthly = r["annual_ctc"] / 12
        basic, hra = round(monthly * 0.40, 2), round(monthly * 0.20, 2)
        special = round(monthly - basic - hra, 2)
        payroll.append({
            "employee_code": r["employee_code"], "period": "2026-10", "basic": basic, "da": 0, "hra": hra,
            "special": special, "leave_encashable_days": extra_rng.randint(0, 30),
            "reimbursements_approved": extra_rng.choice([0, 0, 0, 2500, 8000]),
            "loans_outstanding": extra_rng.choice([0] * 9 + [50000]),
            "tds": round(monthly * 0.08, 2),
        })

    reviews = []
    for r in rows:
        hire = date.fromisoformat(r["hire_date"])
        for idx, (name, start, end) in enumerate(CYCLES):
            if hire > end:
                continue
            last = idx == len(CYCLES) - 1
            calibrated = r["performance_rating"] if last else clamp(r["performance_rating"] + extra_rng.uniform(-0.6, 0.6))
            manager = clamp(calibrated + extra_rng.choice([-0.5, 0, 0, 0, 0.5]))
            low = calibrated <= 2.2
            # Leave a few low ratings undocumented so the "missing evidence" report has something to show.
            documented = not low or extra_rng.random() > 0.3
            reviews.append({
                "employee_code": r["employee_code"], "cycle": name, "self_rating": clamp(calibrated + 0.4),
                "manager_rating": manager, "calibrated_rating": calibrated,
                "manager_comment": ("Missed agreed targets; needs closer support on priorities." if low else
                                    "Met expectations for the quarter.") if documented else "",
            })
    return rows, payroll, reviews


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    people, payroll, reviews = generate(n)
    here = Path(__file__).parent
    write(here / "employees.csv", people)
    write(here / "payroll.csv", payroll)
    write(here / "reviews.csv", reviews)
    print(f"Wrote {len(people)} people, {len(payroll)} payroll rows, {len(reviews)} reviews to {here}")
