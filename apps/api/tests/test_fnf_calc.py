"""FNF components against a worked example. Employee joined 2018-01-15; last working day 2026-11-22 (a Sunday).
Monthly pay: basic ₹40,000, DA 0, HRA ₹20,000, special ₹40,000 (gross ₹1,00,000); 10 encashable leave days;
TDS ₹8,000; reason RED-TEAM (redundancy).

    salary            ₹1,00,000 × 22/30                    = ₹73,333.33
    leave encashment  ₹40,000 ÷ 30 × 10                    = ₹13,333.33
    gratuity          ₹40,000 × 15/26 × 9 years            = ₹2,07,692.31   (8 yrs 10 mths: part-year > 6 months counts)
    retrenchment      ₹40,000 × 15/26 × 9 years            = ₹2,07,692.31
    TDS deduction                                          = ₹8,000.00
    net before rounding ₹4,94,051.28 -> rounded to the rupee ₹4,94,051.00
    payment due: 2 working days after Sunday 22 Nov        = Tue 24 Nov 2026
"""

from datetime import date

from app.compliance.rules import rulebook
from app.fnf.calculator import compute, context_for, what_if
from app.fnf.components import service_years
from tests.conftest import emp

PAY = {"basic": 4_000_000, "da": 0, "hra": 2_000_000, "special": 4_000_000, "leave_encashable_days": 10,
       "tds": 800_000}
LWD = date(2026, 11, 22)


def _ctx(Session, **kw):
    with Session() as db:
        book = rulebook(db, 1)
        book.rules  # load while the session is open
    e = emp("W1", 2.0, hire_date=date(2018, 1, 15))
    args = {"pay": PAY, "lwd": LWD, "pay_in_lieu": False, "notice_days": 30, "shortfall_days": 0,
            "reason_code": "RED-TEAM", **kw}
    return context_for(e, book, args["pay"], args["lwd"], args["pay_in_lieu"], args["notice_days"],
                       args["shortfall_days"], args["reason_code"])


def test_service_years_rounding():
    assert service_years(date(2018, 1, 15), date(2026, 11, 22), 6) == (9, 8, 10)
    assert service_years(date(2018, 1, 15), date(2026, 7, 14), 6) == (8, 8, 5)


def test_worked_example(Session):
    r = compute(_ctx(Session))
    lines = {ln.component: ln.amount_paise for ln in r.lines}
    assert lines == {"salary": 7_333_333, "leave_encashment": 1_333_333, "gratuity": 20_769_231,
                     "retrenchment_compensation": 20_769_231, "tds": 800_000}
    assert r.earnings == 50_205_128 and r.deductions == 800_000
    assert r.net == 49_405_100 and r.rounding_adjustment == -28
    assert r.payment_due_on == date(2026, 11, 24)
    assert r.needs_legal
    rules = {ln.component: ln.rule_key for ln in r.lines}
    assert rules["gratuity"] == "IN-GRAT-001" and rules["retrenchment_compensation"] == "IN-RETR-001"


def test_no_retrenchment_for_non_redundancy_reason(Session):
    lines = {ln.component for ln in compute(_ctx(Session, reason_code="PERF-PIP")).lines}
    assert "retrenchment_compensation" not in lines and "gratuity" in lines


def test_shortfall_and_pay_in_lieu(Session):
    short = {ln.component: ln.amount_paise for ln in compute(_ctx(Session, shortfall_days=5)).lines}
    assert short["notice_shortfall"] == 666_667  # ₹40,000 ÷ 30 × 5
    pil = {ln.component: ln.amount_paise for ln in compute(_ctx(Session, pay_in_lieu=True)).lines}
    assert pil["notice_pay"] == 10_000_000  # gross ₹1,00,000 ÷ 30 × 30
    w = what_if(_ctx(Session))
    assert w["pay_in_lieu"]["net_paise"] - w["work_notice"]["net_paise"] == 10_000_000


def test_gratuity_needs_five_years(Session):
    e_ctx = _ctx(Session)
    e_ctx.employee.hire_date = date(2023, 1, 1)
    assert "gratuity" not in {ln.component for ln in compute(e_ctx).lines}


def test_bonus_for_eligible_wage(Session):
    low = {**PAY, "basic": 1_500_000}
    lines = {ln.component: ln for ln in compute(_ctx(Session, pay=low)).lines}
    # 8.33% × ₹7,000 × 8 months (April to November)
    assert lines["bonus"].amount_paise == 466_480
