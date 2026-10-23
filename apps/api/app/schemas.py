"""Request bodies. Responses are built as plain dicts in the routers (see each router for its shape)."""

from datetime import date

from pydantic import BaseModel, EmailStr, Field

ROLE_PATTERN = "^(admin|hr|manager|legal|finance|approver|viewer)$"


# ------------------------------------------------------------------ auth, users, org
class LoginIn(BaseModel):
    email: str
    password: str


class MfaIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class ActivateIn(BaseModel):
    token: str
    password: str = Field(min_length=10)


class MePatch(BaseModel):
    notify_email: bool | None = None


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern=ROLE_PATTERN)
    password: str = Field(min_length=10)
    employee_code: str | None = None


class UserPatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, pattern=ROLE_PATTERN)
    active: bool | None = None
    password: str | None = Field(default=None, min_length=10)
    employee_code: str | None = None
    reset_mfa: bool | None = None


class OrgSettingsPatch(BaseModel):
    legal_name: str | None = None
    address: str | None = None
    hr_contact_email: EmailStr | None = None
    test_addresses: list[EmailStr] | None = None
    establishment_size: int | None = Field(default=None, ge=0)
    escalation_days: int | None = Field(default=None, ge=1, le=30)


class IntegrationIn(BaseModel):
    type: str
    provider: str
    enabled: bool = False
    config: dict[str, str] = {}
    secrets: dict[str, str] = {}


# ------------------------------------------------------------------ people
class EmployeeIn(BaseModel):
    employee_code: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    department: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=100)
    manager_code: str | None = None
    hire_date: date
    confirmation_date: date | None = None
    employment_type: str = Field(default="permanent", pattern="^(permanent|contract|fixed_term|intern)$")
    contract_end_date: date | None = None
    contract_notice_days: int = Field(default=30, ge=0, le=365)
    annual_ctc_paise: int = Field(ge=0)
    performance_rating: float = Field(ge=1, le=5)
    potential_rating: float = Field(ge=1, le=5)
    critical_skill_score: float = Field(ge=1, le=5)
    gender: str = Field(min_length=1, max_length=20)
    age_band: str = Field(min_length=1, max_length=20)
    leave_status: str = Field(default="none", pattern="^(none|maternity|medical|other)$")
    protected_flag: bool = False
    legal_hold: bool = False
    custom_metrics: dict[str, float] = {}


class EmployeePatch(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    department: str | None = None
    role: str | None = None
    location: str | None = None
    manager_code: str | None = None
    hire_date: date | None = None
    confirmation_date: date | None = None
    employment_type: str | None = Field(default=None, pattern="^(permanent|contract|fixed_term|intern)$")
    contract_end_date: date | None = None
    contract_notice_days: int | None = Field(default=None, ge=0, le=365)
    annual_ctc_paise: int | None = Field(default=None, ge=0)
    performance_rating: float | None = Field(default=None, ge=1, le=5)
    potential_rating: float | None = Field(default=None, ge=1, le=5)
    critical_skill_score: float | None = Field(default=None, ge=1, le=5)
    gender: str | None = None
    age_band: str | None = None
    leave_status: str | None = Field(default=None, pattern="^(none|maternity|medical|other)$")
    protected_flag: bool | None = None
    legal_hold: bool | None = None
    custom_metrics: dict[str, float] | None = None


class PayrollInputIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")
    data: dict[str, float]


# ------------------------------------------------------------------ performance
class CycleIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    period_start: date
    period_end: date
    scale_max: int = Field(default=5, ge=3, le=10)


class ReviewIn(BaseModel):
    employee_id: int
    self_rating: float | None = Field(default=None, ge=1, le=10)
    self_comment: str | None = None
    manager_rating: float | None = Field(default=None, ge=1, le=10)
    manager_comment: str | None = None
    peer_input: str | None = None


class CalibrateIn(BaseModel):
    calibrated_rating: float = Field(ge=1, le=10)


class GoalIn(BaseModel):
    employee_id: int
    cycle_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    weight: float = Field(default=1, gt=0)
    target: str = ""
    due_date: date | None = None
    objective: str | None = None


class ProgressIn(BaseModel):
    pct: float = Field(ge=0, le=100)
    note: str = ""


class ActionIn(BaseModel):
    text: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    due_date: date | None = None


class CheckinIn(BaseModel):
    employee_id: int
    scheduled_for: date
    held_on: date | None = None
    summary: str = ""
    sentiment: str = Field(default="neutral", pattern="^(positive|neutral|concern)$")
    private_note: str | None = None
    actions: list[ActionIn] = []


class FeedbackIn(BaseModel):
    employee_id: int
    strength: str = ""
    improvement: str = ""
    example: str = ""
    given_on: date
    author_visible_to_employee: bool = False


class PipIn(BaseModel):
    employee_id: int
    reason_category: str = Field(min_length=1, max_length=50)
    gaps: str = Field(min_length=10)
    success_criteria: str = Field(min_length=10)
    support: str = ""
    start_date: date
    end_date: date | None = None
    checkin_dates: list[date] = []


class MilestoneIn(BaseModel):
    on_date: date
    evidence_reviewed: str = Field(min_length=5)
    outcome: str = Field(pattern="^(met|partially_met|not_met)$")
    notes: str = ""


class AckIn(BaseModel):
    status: str = Field(pattern="^(acknowledged|declined)$")


class PipCloseIn(BaseModel):
    outcome: str = Field(pattern="^(met|partially_met|not_met)$")
    final_review: str = Field(min_length=10)
    final_review_on: date


# ------------------------------------------------------------------ KPIs and plans
class KpiIn(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=100)
    description: str = ""
    expression: str
    higher_is_better: bool = True


class KpiPreviewIn(BaseModel):
    expression: str


class Filters(BaseModel):
    departments: list[str] = []
    locations: list[str] = []
    roles: list[str] = []


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    selection_method: str = Field(default="score_ranked", pattern="^(score_ranked|role_redundancy|manual_list)$")
    target_count: int | None = Field(default=None, ge=1)
    target_cost_paise: int | None = Field(default=None, ge=1)
    filters: Filters = Filters()
    weights: dict[str, float] = {}
    eliminated_roles: list[str] = []
    manual_codes: list[str] = []
    as_of_date: date | None = None


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    selection_method: str | None = Field(default=None, pattern="^(score_ranked|role_redundancy|manual_list)$")
    target_count: int | None = Field(default=None, ge=1)
    target_cost_paise: int | None = Field(default=None, ge=1)
    filters: Filters | None = None
    weights: dict[str, float] | None = None
    eliminated_roles: list[str] | None = None
    manual_codes: list[str] | None = None


class OverrideIn(BaseModel):
    employee_id: int
    action: str = Field(pattern="^(include|exclude)$")
    justification: str = Field(min_length=10)


class RevokeIn(BaseModel):
    justification: str = Field(min_length=10)


class DecisionIn(BaseModel):
    approve: bool
    comment: str | None = None
    fairness_justification: str | None = None


# ------------------------------------------------------------------ rules, reasons, notices
class VerifyIn(BaseModel):
    rule_ids: list[int] | None = None
    verified_by: str = Field(min_length=3)
    verified_on: date
    note: str = ""


class TemplatePatch(BaseModel):
    subject: str | None = None
    body: str | None = None
    send_to_personal: bool | None = None
    attach_pdf: bool | None = None
    encrypt_attachment: bool | None = None


class DraftsIn(BaseModel):
    template_id: int
    case_ids: list[int] | None = None


class DraftPatch(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)


class BatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    draft_ids: list[int] = Field(min_length=1)


class ExcludeIn(BaseModel):
    message_id: int
    excluded: bool


# ------------------------------------------------------------------ exit cases, FNF, documents, clearance, grievances
class CasesFromPlanIn(BaseModel):
    plan_id: int


class ReasonIn(BaseModel):
    reason_code: str
    reason_detail: str | None = None
    evidence_ids: list[int] = []


class DatesIn(BaseModel):
    notice_date: date
    pay_in_lieu: bool = False


class LastDayIn(BaseModel):
    actual_last_day: date | None = None


class TextIn(BaseModel):
    text: str = Field(min_length=3)


class TaskPatch(BaseModel):
    status: str = Field(pattern="^(open|done|cancelled)$")


class MarkPaidIn(BaseModel):
    reference: str = Field(min_length=3, max_length=100)


class DocumentIn(BaseModel):
    kind: str
    password_protect: bool = False


class ClearanceIn(BaseModel):
    status: str
    note: str | None = None


class GrievanceIn(BaseModel):
    exit_case_id: int
    category: str
    description: str = Field(min_length=10)


class SelfGrievanceIn(BaseModel):
    category: str
    description: str = Field(min_length=10)


class GrievanceDecisionIn(BaseModel):
    findings: str = Field(min_length=5)
    outcome: str = Field(pattern="^(upheld|partly_upheld|rejected)$")
    reasons: str = Field(min_length=5)


class AppealIn(BaseModel):
    grounds: str = Field(min_length=10)


class AppealDecisionIn(BaseModel):
    outcome: str = Field(pattern="^(upheld|partly_upheld|rejected)$")
    reasons: str = Field(min_length=5)


# ------------------------------------------------------------------ AI
class ExplainIn(BaseModel):
    employee_id: int


class QuestionIn(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
