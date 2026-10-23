"""Notice period and last working day, with the rules that produced them."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.compliance.rules import RuleBook
from app.models import Employee

NOTICE_RULES = ["IN-NOTICE-001", "IN-NOTICE-002", "IN-NOTICE-003"]


@dataclass
class NoticeResult:
    days: int
    last_working_day: date
    pay_in_lieu: bool
    trace: list[dict] = field(default_factory=list)


def compute(employee: Employee, book: RuleBook, notice_date: date, pay_in_lieu: bool) -> NoticeResult:
    trace: list[dict] = []
    rule = book.first_applicable(NOTICE_RULES, employee)
    statutory = int((rule.value or {}).get("days", 0)) if rule else 0
    trace.append({"rule": rule.rule_key if rule else None,
                  "step": f"Statutory notice for {employee.employment_type}: {statutory} days"})
    days = statutory
    longer = book.get("IN-NOTICE-004")
    if longer and (longer.value or {}).get("use_contract_if_longer") and employee.contract_notice_days > days:
        days = employee.contract_notice_days
        trace.append({"rule": "IN-NOTICE-004", "step": f"Contract notice of {days} days is longer, so it applies"})
    else:
        trace.append({"rule": "IN-NOTICE-004" if longer else None,
                      "step": f"Contract notice ({employee.contract_notice_days} days) is not longer"})
    if pay_in_lieu:
        allowed = rule is None or (rule.value or {}).get("pay_in_lieu_allowed", True)
        if not allowed:
            raise ValueError("Pay in lieu of notice isn't allowed by the applicable rule")
        lwd = notice_date
        trace.append({"rule": rule.rule_key if rule else None,
                      "step": f"Paid in lieu of notice: last working day is the notice date ({lwd})"})
    else:
        lwd = notice_date + timedelta(days=days)
        trace.append({"rule": None, "step": f"Notice date {notice_date} + {days} days = {lwd}"})
    return NoticeResult(days=days, last_working_day=lwd, pay_in_lieu=pay_in_lieu, trace=trace)


def shortfall_days(computed_lwd: date | None, actual_last_day: date | None, pay_in_lieu: bool) -> int:
    if pay_in_lieu or not computed_lwd or not actual_last_day:
        return 0
    return max(0, (computed_lwd - actual_last_day).days)
