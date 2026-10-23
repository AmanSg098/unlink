"""Full and final settlement components. Each is a named function that reads the ruleset and returns a line
citing the rule, the formula, and the inputs. Money is integer paise; division uses Decimal and rounds half-up
to the paisa. Payroll inputs come from `payroll_inputs.data` (amounts in paise, counts in days/months):

    basic, da, hra, special          monthly components
    days_in_month                    defaults to the calendar days of the last working day's month
    days_worked_final_month          defaults to the last working day's day of month
    salary_paid_final_month          already paid for the final month (default 0)
    leave_encashable_days            encashable leave balance
    bonus_months_worked              months worked in the bonus year (default: since 1 April)
    bonus_already_paid
    reimbursements_approved
    loans_outstanding, advances, asset_recovery, training_bond, other_recovery
    tds                              tax deducted at source, as computed by payroll
"""

import calendar
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.compliance.rules import RuleBook
from app.models import Employee
from app.reasons import REDUNDANCY


def paise(x: Decimal | int | float) -> int:
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def rupees(p: int) -> str:
    return f"₹{p / 100:,.2f}"


@dataclass
class Line:
    kind: str  # earning | deduction
    component: str
    label: str
    amount_paise: int
    rule_key: str | None
    formula: str
    inputs: dict = field(default_factory=dict)


@dataclass
class FnfContext:
    employee: Employee
    book: RuleBook
    pay: dict
    last_working_day: date
    pay_in_lieu: bool
    notice_days: int
    shortfall_days: int
    reason_code: str | None

    def wage(self, components: list[str]) -> int:
        return sum(int(self.pay.get(c, 0)) for c in components)

    def rule(self, key: str) -> dict:
        return self.book.value(key) or {}


def service_years(hire: date, lwd: date, round_up_months: int | None) -> tuple[int, int, int]:
    """(counted years, completed years, extra months). A part-year over `round_up_months` counts as a year."""
    months = (lwd.year - hire.year) * 12 + (lwd.month - hire.month) - (1 if lwd.day < hire.day else 0)
    completed, extra = divmod(max(months, 0), 12)
    counted = completed + (1 if round_up_months is not None and extra > round_up_months else 0)
    return counted, completed, extra


def salary_final_month(c: FnfContext) -> Line | None:
    r = c.rule("IN-PAY-003")
    comps = r.get("wage_components", ["basic", "da", "hra", "special"])
    gross = c.wage(comps)
    dim = int(c.pay.get("days_in_month") or calendar.monthrange(c.last_working_day.year, c.last_working_day.month)[1])
    worked = int(c.pay.get("days_worked_final_month", c.last_working_day.day))
    paid = int(c.pay.get("salary_paid_final_month", 0))
    amount = paise(Decimal(gross) * worked / dim) - paid
    return Line("earning", "salary", "Salary for days worked in the final month", max(amount, 0), "IN-PAY-003",
                f"monthly gross {rupees(gross)} × {worked}/{dim} days − already paid {rupees(paid)}",
                {"gross_monthly": gross, "days_worked": worked, "days_in_month": dim, "already_paid": paid})


def leave_encashment(c: FnfContext) -> Line | None:
    days = Decimal(str(c.pay.get("leave_encashable_days", 0)))
    if days <= 0:
        return None
    r = c.rule("IN-LEAVE-001")
    comps, div = r.get("wage_components", ["basic", "da"]), int(r.get("wage_divisor", 30))
    w = c.wage(comps)
    return Line("earning", "leave_encashment", "Leave encashment", paise(Decimal(w) / div * days), "IN-LEAVE-001",
                f"({' + '.join(comps)}) {rupees(w)} ÷ {div} × {days} days",
                {"wage": w, "divisor": div, "days": str(days)})


def gratuity(c: FnfContext) -> Line | None:
    r = c.rule("IN-GRAT-001")
    if not r:
        return None
    counted, completed, extra = service_years(c.employee.hire_date, c.last_working_day, r.get("round_up_months"))
    fixed = c.employee.employment_type == "fixed_term"
    min_years = r.get("min_years_fixed_term", 1) if fixed else r.get("min_years", 5)
    if completed < min_years:
        return None
    w = c.wage(r.get("wage_components", ["basic", "da"]))
    raw = paise(Decimal(w) * r["days_per_year"] / r["wage_divisor"] * counted)
    cap = int(r.get("cap_paise", raw))
    amount = min(raw, cap)
    capped = " (capped)" if raw > cap else ""
    return Line("earning", "gratuity", "Gratuity", amount, "IN-GRAT-001",
                f"{rupees(w)} × {r['days_per_year']}/{r['wage_divisor']} × {counted} years{capped}",
                {"wage": w, "years_counted": counted, "completed_years": completed, "extra_months": extra,
                 "cap_paise": cap})


def retrenchment_compensation(c: FnfContext) -> Line | None:
    if c.reason_code not in REDUNDANCY or not c.book.applies("IN-RETR-001", c.employee, c.reason_code):
        return None
    r = c.rule("IN-RETR-001")
    if (c.last_working_day - c.employee.hire_date).days < r.get("min_service_days", 365):
        return None
    counted, completed, extra = service_years(c.employee.hire_date, c.last_working_day, 6)
    w = c.wage(r.get("wage_components", ["basic", "da"]))
    amount = paise(Decimal(w) * r["days_per_completed_year"] / r["wage_divisor"] * counted)
    return Line("earning", "retrenchment_compensation", "Retrenchment compensation", amount, "IN-RETR-001",
                f"{rupees(w)} × {r['days_per_completed_year']}/{r['wage_divisor']} × {counted} years",
                {"wage": w, "years_counted": counted, "completed_years": completed, "extra_months": extra})


def notice_pay(c: FnfContext) -> Line | None:
    if not c.pay_in_lieu or c.notice_days <= 0:
        return None
    r = c.rule("IN-PAY-001")
    comps, div = r.get("wage_components", ["basic", "da", "hra", "special"]), int(r.get("wage_divisor", 30))
    w = c.wage(comps)
    return Line("earning", "notice_pay", "Pay in lieu of notice", paise(Decimal(w) / div * c.notice_days),
                "IN-PAY-001", f"monthly gross {rupees(w)} ÷ {div} × {c.notice_days} notice days",
                {"wage": w, "divisor": div, "notice_days": c.notice_days})


def bonus(c: FnfContext) -> Line | None:
    r = c.rule("IN-BONUS-001")
    if not r:
        return None
    w = c.wage(["basic", "da"])
    if w > r["eligibility_monthly_wage_paise"]:
        return None
    lwd = c.last_working_day
    fy_start = date(lwd.year if lwd.month >= 4 else lwd.year - 1, 4, 1)
    if (lwd - max(fy_start, c.employee.hire_date)).days < r.get("min_days_worked", 30):
        return None
    months = Decimal(str(c.pay.get("bonus_months_worked",
                                   (lwd.year - fy_start.year) * 12 + lwd.month - fy_start.month + 1)))
    calc = max(r["calc_monthly_wage_paise"], 0)
    already = int(c.pay.get("bonus_already_paid", 0))
    amount = paise(Decimal(calc) * Decimal(str(r["rate_pct"])) / 100 * months) - already
    if amount <= 0:
        return None
    return Line("earning", "bonus", "Statutory bonus (pro-rated)", amount, "IN-BONUS-001",
                f"{r['rate_pct']}% × {rupees(calc)} × {months} months − already paid {rupees(already)}",
                {"calc_wage": calc, "months": str(months), "already_paid": already})


def reimbursements(c: FnfContext) -> Line | None:
    v = int(c.pay.get("reimbursements_approved", 0))
    return Line("earning", "reimbursements", "Approved reimbursements", v, None, "as approved in payroll",
                {"amount": v}) if v else None


def notice_shortfall(c: FnfContext) -> Line | None:
    r = c.rule("IN-PAY-002")
    if c.shortfall_days <= 0 or not r.get("allowed"):
        return None
    comps, div = r.get("wage_components", ["basic", "da"]), int(r.get("wage_divisor", 30))
    w = c.wage(comps)
    return Line("deduction", "notice_shortfall", "Notice shortfall recovery",
                paise(Decimal(w) / div * c.shortfall_days), "IN-PAY-002",
                f"{rupees(w)} ÷ {div} × {c.shortfall_days} days not served",
                {"wage": w, "divisor": div, "shortfall_days": c.shortfall_days})


def _flat(kind: str, component: str, label: str, keys: list[str]) -> Callable[[FnfContext], Line | None]:
    def fn(c: FnfContext) -> Line | None:
        parts = {k: int(c.pay.get(k, 0)) for k in keys}
        total = sum(parts.values())
        return Line(kind, component, label, total, None, " + ".join(keys) + " from payroll", parts) if total else None
    fn.__name__ = component
    return fn


COMPONENTS: list[Callable[[FnfContext], Line | None]] = [
    salary_final_month, leave_encashment, gratuity, retrenchment_compensation, notice_pay, bonus, reimbursements,
    notice_shortfall,
    _flat("deduction", "loans_advances", "Loans and advances outstanding", ["loans_outstanding", "advances"]),
    _flat("deduction", "recoveries", "Asset, bond and other recoveries", ["asset_recovery", "training_bond",
                                                                          "other_recovery"]),
    _flat("deduction", "tds", "Tax deducted at source (from payroll)", ["tds"]),
]
