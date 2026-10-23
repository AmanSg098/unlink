"""Approval sequences: which roles approve each kind of item, in order.

Admin may act on any step. Separation of duties is enforced by the engine (workflow/approvals.py):
the preparer can't approve, and one person can't approve two steps of the same round.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    name: str
    roles: tuple[str, ...]
    label: str
    condition: str | None = None  # step runs only when this condition flag is true


SEQUENCES: dict[str, list[Step]] = {
    "plan": [
        Step("legal_review", ("legal",), "Legal review"),
        Step("finance_review", ("finance",), "Finance review"),
        Step("final_approval", ("approver",), "Final approval"),
    ],
    "notice_batch": [Step("send_approval", ("legal", "approver"), "Approve for sending")],
    "fnf": [
        Step("finance_review", ("finance",), "Finance review"),
        Step("legal_review", ("legal",), "Legal review (compensation or gratuity)", condition="needs_legal"),
    ],
    "exit_effective": [Step("approval", ("approver",), "Approve exit as effective")],
    "hris_push": [Step("approval", ("finance",), "Approve write to HRIS")],
    "reason_other": [Step("legal_approval", ("legal",), "Legal approval of an 'Other' reason")],
    "clearance_exception": [Step("approval", ("approver",), "Approve relieving letter without full clearance")],
    "template": [Step("legal_approval", ("legal",), "Legal approval of template")],
}
