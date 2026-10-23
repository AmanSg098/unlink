"""CSV imports: people and payroll inputs. Errors are reported by line number only (never row contents)."""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.deps import Ctx
from app.models import EMPLOYMENT_TYPES, Employee, PayrollInput
from app.people import apply_changes

REQUIRED = [
    "employee_code", "full_name", "department", "role", "location", "hire_date", "annual_ctc",
    "performance_rating", "potential_rating", "critical_skill_score", "gender", "age_band",
]
OPTIONAL_TEXT = ["email", "personal_email", "manager_code"]
OPTIONAL_DATES = ["confirmation_date", "contract_end_date"]
RATINGS = ["performance_rating", "potential_rating", "critical_skill_score"]
TRUE = {"1", "true", "yes", "y"}
METRIC_PREFIX = "kpi_"

PAYROLL_REQUIRED = ["employee_code", "period", "basic", "da", "hra", "special"]
PAYROLL_MONEY = ["basic", "da", "hra", "special", "salary_paid_final_month", "bonus_already_paid",
                 "reimbursements_approved", "loans_outstanding", "advances", "asset_recovery", "training_bond",
                 "other_recovery", "tds"]
PAYROLL_NUMBERS = ["leave_encashable_days", "days_worked_final_month", "days_in_month", "bonus_months_worked"]


def to_paise(rupees: str) -> int:
    return int((Decimal(rupees.strip().replace(",", "")) * 100).quantize(Decimal(1)))


def _date(v: str | None) -> date | None:
    v = (v or "").strip()
    return date.fromisoformat(v) if v else None


def parse_people_csv(text: str) -> tuple[dict[str, dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    cols = reader.fieldnames or []
    missing = [c for c in REQUIRED if c not in cols]
    if missing:
        return {}, [f"missing columns: {', '.join(missing)}"]
    metric_cols = [c for c in cols if c.startswith(METRIC_PREFIX) and len(c) > len(METRIC_PREFIX)]
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        try:
            g = {k: (row.get(k) or "").strip() for k in cols}
            if not g["employee_code"]:
                raise ValueError("employee_code is empty")
            etype = g.get("employment_type") or "permanent"
            if etype not in EMPLOYMENT_TYPES:
                raise ValueError("employment_type")
            fields = {
                "employee_code": g["employee_code"], "full_name": g["full_name"], "department": g["department"],
                "role": g["role"], "location": g["location"], "hire_date": date.fromisoformat(g["hire_date"]),
                "annual_ctc_paise": to_paise(g["annual_ctc"]), "gender": g["gender"], "age_band": g["age_band"],
                **{k: float(g[k]) for k in RATINGS},
                **{k: (g.get(k) or None) for k in OPTIONAL_TEXT},
                **{k: _date(g.get(k)) for k in OPTIONAL_DATES},
                "employment_type": etype,
                "contract_notice_days": int(g.get("contract_notice_days") or 30),
                "leave_status": (g.get("leave_status") or "none").lower(),
                "protected_flag": (g.get("protected_flag") or "").lower() in TRUE,
                # Blank cells are omitted so metric("name", default) falls back to its default.
                "custom_metrics": {c[len(METRIC_PREFIX):].lower(): float(g[c]) for c in metric_cols if g.get(c)},
            }
            if not all(1 <= fields[k] <= 5 for k in RATINGS):
                raise ValueError("rating out of range")
        except (ValueError, InvalidOperation) as exc:
            errors.append(f"line {line}: {type(exc).__name__}")
            continue
        rows[fields["employee_code"]] = fields
    return rows, errors


def import_people(db: Session, ctx: Ctx, text: str) -> dict:
    rows, errors = parse_people_csv(text)
    existing = {e.employee_code: e for e in db.scalars(select(Employee).where(Employee.org_id == ctx.org_id))}
    created = updated = 0
    for code, fields in rows.items():
        e = existing.get(code)
        if e is None:
            db.add(Employee(org_id=ctx.org_id, **fields))
            created += 1
        elif apply_changes(db, ctx, e, fields, action="import_update"):
            updated += 1
    db.flush()
    audit.record(db, ctx, "employee", None, "import", None,
                 {"created": created, "updated": updated, "errors": len(errors)})
    return {"created": created, "updated": updated, "errors": errors}


def import_payroll(db: Session, ctx: Ctx, text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text))
    cols = reader.fieldnames or []
    missing = [c for c in PAYROLL_REQUIRED if c not in cols]
    if missing:
        return {"created": 0, "updated": 0, "errors": [f"missing columns: {', '.join(missing)}"]}
    emps = {e.employee_code: e for e in db.scalars(select(Employee).where(Employee.org_id == ctx.org_id))}
    created = updated = 0
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        try:
            code = (row.get("employee_code") or "").strip()
            e = emps.get(code)
            if e is None:
                raise ValueError("unknown employee_code")
            period = row["period"].strip()
            if len(period) != 7 or period[4] != "-":
                raise ValueError("period must be YYYY-MM")
            data = {k: to_paise(row[k]) for k in PAYROLL_MONEY if (row.get(k) or "").strip()}
            data |= {k: float(row[k]) for k in PAYROLL_NUMBERS if (row.get(k) or "").strip()}
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append(f"line {line}: {type(exc).__name__}")
            continue
        pi = db.scalar(select(PayrollInput).where(PayrollInput.employee_id == e.id, PayrollInput.period == period))
        if pi is None:
            db.add(PayrollInput(org_id=ctx.org_id, employee_id=e.id, period=period, data=data, source="import",
                                updated_by=ctx.user))
            created += 1
        else:
            pi.data, pi.updated_by = data, ctx.user
            updated += 1
        e.salary_breakup = {k: data.get(k, 0) for k in ("basic", "da", "hra", "special")}
    db.flush()
    audit.record(db, ctx, "payroll", None, "import", None, {"created": created, "updated": updated,
                                                            "errors": len(errors)})
    return {"created": created, "updated": updated, "errors": errors}
