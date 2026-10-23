"""Compute an FNF statement from components, with totals, rounding and payment due date."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.compliance.rules import RuleBook
from app.fnf.components import COMPONENTS, FnfContext, Line


@dataclass
class FnfResult:
    lines: list[Line]
    earnings: int
    deductions: int
    net: int
    rounding_adjustment: int
    needs_legal: bool
    payment_due_on: date | None


def add_working_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def compute(ctx: FnfContext) -> FnfResult:
    lines = [ln for fn in COMPONENTS if (ln := fn(ctx)) is not None and ln.amount_paise != 0]
    earnings = sum(ln.amount_paise for ln in lines if ln.kind == "earning")
    deductions = sum(ln.amount_paise for ln in lines if ln.kind == "deduction")
    raw = earnings - deductions
    step = int((ctx.book.value("IN-FNF-002") or {}).get("round_to_paise", 1)) or 1
    # Round half up to the nearest step (e.g. a rupee), for positive and negative nets alike.
    net = (abs(raw) + step // 2) // step * step * (1 if raw >= 0 else -1)
    due_days = (ctx.book.value("IN-FNF-001") or {}).get("working_days_after_exit")
    due = add_working_days(ctx.last_working_day, int(due_days)) if due_days is not None else None
    needs_legal = any(ln.component in ("gratuity", "retrenchment_compensation") for ln in lines)
    return FnfResult(lines, earnings, deductions, net, net - raw, needs_legal, due)


def what_if(ctx: FnfContext) -> dict:
    """Compare paying notice in lieu against the employee working it out."""
    out = {}
    for label, pil in (("pay_in_lieu", True), ("work_notice", False)):
        alt = FnfContext(**{**ctx.__dict__, "pay_in_lieu": pil, "shortfall_days": 0 if pil else ctx.shortfall_days})
        r = compute(alt)
        out[label] = {"net_paise": r.net, "earnings_paise": r.earnings, "deductions_paise": r.deductions}
    return out


def context_for(employee, book: RuleBook, pay: dict, lwd: date, pay_in_lieu: bool, notice_days: int,
                shortfall_days: int, reason_code: str | None) -> FnfContext:
    return FnfContext(employee=employee, book=book, pay=pay or {}, last_working_day=lwd, pay_in_lieu=pay_in_lieu,
                      notice_days=notice_days, shortfall_days=shortfall_days, reason_code=reason_code)
