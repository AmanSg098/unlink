"""Database models. Every table except `orgs` carries org_id; every query filters on it.

Money is stored as integer paise. Times are stored in UTC.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def org_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("orgs.id"), index=True)


def created_ts() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------------------------
# Organisation, users, sessions
# --------------------------------------------------------------------------------------------

class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(20), default="IN")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    # test_addresses, establishment_size, hr_contact_email, legal_name, escalation_days,
    # retention overrides, reason_wording_approvals, pip_status_map
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


ROLES = ("admin", "hr", "manager", "legal", "finance", "approver", "viewer")


class User(Base):
    """Staff account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    email: Mapped[str] = mapped_column(String(200), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Links a staff account (typically a manager) to their own employee record / reporting line.
    employee_code: Mapped[str | None] = mapped_column(String(50))
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_ts()


class EmployeeAccount(Base):
    """Employee self-service login, limited to the employee's own case."""

    __tablename__ = "employee_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(300))
    invite_token_hash: Mapped[str | None] = mapped_column(String(64))
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_ts()


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    employee_account_id: Mapped[int | None] = mapped_column(ForeignKey("employee_accounts.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_ts()
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), index=True)
    account_key: Mapped[str] = mapped_column(String(200), index=True)
    ip: Mapped[str | None] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = created_ts()


class Notification(Base):
    """In-app notification. Titles never contain employee names or amounts."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(300))
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_ts()


# --------------------------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------------------------

EMPLOYMENT_TYPES = ("permanent", "contract", "fixed_term", "intern")
EMPLOYEE_STATUSES = ("active", "on_notice", "exited", "on_hold")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("org_id", "employee_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_code: Mapped[str] = mapped_column(String(50))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    personal_email: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    manager_code: Mapped[str | None] = mapped_column(String(50), index=True)
    hire_date: Mapped[date] = mapped_column(Date)
    confirmation_date: Mapped[date | None] = mapped_column(Date)
    employment_type: Mapped[str] = mapped_column(String(20), default="permanent")
    contract_end_date: Mapped[date | None] = mapped_column(Date)
    contract_notice_days: Mapped[int] = mapped_column(Integer, default=30)
    annual_ctc_paise: Mapped[int] = mapped_column(BigInteger)
    # Monthly components in paise: {"basic", "da", "hra", "special"}
    salary_breakup: Mapped[dict] = mapped_column(JSON, default=dict)
    performance_rating: Mapped[float] = mapped_column(Float)
    potential_rating: Mapped[float] = mapped_column(Float)
    critical_skill_score: Mapped[float] = mapped_column(Float)
    # Fairness analysis only, never scoring inputs.
    gender: Mapped[str] = mapped_column(String(20))
    age_band: Mapped[str] = mapped_column(String(20))
    leave_status: Mapped[str] = mapped_column(String(30), default="none")
    protected_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    pseudonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeHistory(Base):
    __tablename__ = "employee_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    field: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON)
    new_value: Mapped[dict | list | str | int | float | None] = mapped_column(JSON)
    changed_by: Mapped[str] = mapped_column(String(200))
    changed_at: Mapped[datetime] = created_ts()


# --------------------------------------------------------------------------------------------
# Performance
# --------------------------------------------------------------------------------------------

class ReviewCycle(Base):
    __tablename__ = "review_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    name: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    scale_max: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | calibrating | closed
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("cycle_id", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    cycle_id: Mapped[int] = mapped_column(ForeignKey("review_cycles.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    self_rating: Mapped[float | None] = mapped_column(Float)
    self_comment: Mapped[str | None] = mapped_column(Text)
    manager_rating: Mapped[float | None] = mapped_column(Float)
    manager_comment: Mapped[str | None] = mapped_column(Text)
    peer_input: Mapped[str | None] = mapped_column(Text)
    calibrated_rating: Mapped[float | None] = mapped_column(Float)
    calibrated_by: Mapped[str | None] = mapped_column(String(200))
    calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(200))


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("review_cycles.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    target: Mapped[str] = mapped_column(String(200), default="")
    due_date: Mapped[date | None] = mapped_column(Date)
    objective: Mapped[str | None] = mapped_column(String(200))
    progress_pct: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


class GoalProgress(Base):
    __tablename__ = "goal_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    pct: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(Text, default="")
    recorded_by: Mapped[str] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = created_ts()


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    scheduled_for: Mapped[date] = mapped_column(Date)
    held_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text, default="")
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")  # positive | neutral | concern
    # Manager-only private note: visible to its author only, never in HR reports.
    private_note_enc: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


class CheckinAction(Base):
    __tablename__ = "checkin_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    checkin_id: Mapped[int] = mapped_column(ForeignKey("checkins.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    author: Mapped[str] = mapped_column(String(200))
    strength: Mapped[str] = mapped_column(Text, default="")
    improvement: Mapped[str] = mapped_column(Text, default="")
    example: Mapped[str] = mapped_column(Text, default="")
    given_on: Mapped[date] = mapped_column(Date)
    author_visible_to_employee: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_ts()


class Pip(Base):
    __tablename__ = "pips"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    reason_category: Mapped[str] = mapped_column(String(50))
    gaps: Mapped[str] = mapped_column(Text)
    success_criteria: Mapped[str] = mapped_column(Text)
    support: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    checkin_dates: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | active | closed
    outcome: Mapped[str | None] = mapped_column(String(20))  # met | partially_met | not_met
    final_review: Mapped[str | None] = mapped_column(Text)
    final_review_on: Mapped[date | None] = mapped_column(Date)
    employee_ack: Mapped[str] = mapped_column(String(20), default="pending")  # pending | acknowledged | declined
    employee_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proposed_by: Mapped[str] = mapped_column(String(200))
    activated_by: Mapped[str | None] = mapped_column(String(200))
    closed_by: Mapped[str | None] = mapped_column(String(200))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_ts()


class PipMilestone(Base):
    __tablename__ = "pip_milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    pip_id: Mapped[int] = mapped_column(ForeignKey("pips.id", ondelete="CASCADE"), index=True)
    on_date: Mapped[date] = mapped_column(Date)
    evidence_reviewed: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20))  # met | partially_met | not_met
    notes: Mapped[str] = mapped_column(Text, default="")
    manager_signed_by: Mapped[str] = mapped_column(String(200))
    manager_signed_at: Mapped[datetime] = created_ts()
    employee_ack: Mapped[str] = mapped_column(String(20), default="pending")
    employee_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evidence(Base):
    """Attachment metadata. The file itself is AES-GCM encrypted in storage."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[int] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(200))
    scan_status: Mapped[str] = mapped_column(String(20))  # clean | not_scanned
    uploaded_by: Mapped[str] = mapped_column(String(200))
    uploaded_at: Mapped[datetime] = created_ts()


# --------------------------------------------------------------------------------------------
# KPIs, plans, approvals
# --------------------------------------------------------------------------------------------

class CustomKpi(Base):
    __tablename__ = "custom_kpis"
    __table_args__ = (UniqueConstraint("org_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    expression: Mapped[str] = mapped_column(Text)
    higher_is_better: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


SELECTION_METHODS = ("score_ranked", "role_redundancy", "manual_list")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    target_count: Mapped[int | None] = mapped_column(Integer)
    target_cost_paise: Mapped[int | None] = mapped_column(BigInteger)
    selection_method: Mapped[str] = mapped_column(String(20), default="score_ranked")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)  # departments, locations, roles
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    eliminated_roles: Mapped[list] = mapped_column(JSON, default=list)
    manual_codes: Mapped[list] = mapped_column(JSON, default=list)
    as_of_date: Mapped[date] = mapped_column(Date)
    ruleset_id: Mapped[int | None] = mapped_column(ForeignKey("rulesets.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | submitted | approved
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[str | None] = mapped_column(String(200))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fairness_justification: Mapped[str | None] = mapped_column(Text)
    kpi_snapshot: Mapped[dict | None] = mapped_column(JSON)


class PlanResult(Base):
    __tablename__ = "plan_results"
    __table_args__ = (UniqueConstraint("plan_id", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    contributions: Mapped[dict] = mapped_column(JSON, default=dict)
    algo_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    final_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(200))


class PlanOverride(Base):
    __tablename__ = "plan_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    action: Mapped[str] = mapped_column(String(20))  # include | exclude
    justification: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_by: Mapped[str | None] = mapped_column(String(200))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_justification: Mapped[str | None] = mapped_column(Text)


class Approval(Base):
    """One step of an approval sequence for any entity, bound to the content hash it approved."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    sequence: Mapped[str] = mapped_column(String(30))
    round: Mapped[int] = mapped_column(Integer, default=1)
    step_index: Mapped[int] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(String(40))
    roles: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|superseded|skipped
    prepared_by: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_ts()


# --------------------------------------------------------------------------------------------
# Jurisdiction rules
# --------------------------------------------------------------------------------------------

class Ruleset(Base):
    __tablename__ = "rulesets"
    __table_args__ = (UniqueConstraint("org_id", "key", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    key: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(20))
    jurisdiction: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    source_file: Mapped[str] = mapped_column(String(300))
    file_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    loaded_at: Mapped[datetime] = created_ts()


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("ruleset_id", "rule_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    ruleset_id: Mapped[int] = mapped_column(ForeignKey("rulesets.id", ondelete="CASCADE"), index=True)
    rule_key: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50))
    applies_to: Mapped[dict] = mapped_column(JSON, default=dict)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(Text)
    effective_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str | None] = mapped_column(String(200))
    verified_on: Mapped[date | None] = mapped_column(Date)
    verified_note: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------------------------
# Notices
# --------------------------------------------------------------------------------------------

class NoticeTemplate(Base):
    __tablename__ = "notice_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    key: Mapped[str] = mapped_column(String(60))
    type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(String(50), default="india")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | legal_approved | retired
    send_to_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    attach_pdf: Mapped[bool] = mapped_column(Boolean, default=True)
    encrypt_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("notice_templates.id"))
    created_by: Mapped[str] = mapped_column(String(200))
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_ts()


class NoticeDraft(Base):
    __tablename__ = "notice_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int] = mapped_column(ForeignKey("exit_cases.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("notice_templates.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    subject: Mapped[str] = mapped_column(String(300))
    body_enc: Mapped[str] = mapped_column(Text)
    merged_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    flagged_terms: Mapped[list] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | in_batch | sent | superseded
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


class NoticeBatch(Base):
    __tablename__ = "notice_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|pending_approval|approved|released|completed
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()
    test_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(200))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NoticeMessage(Base):
    __tablename__ = "notice_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    batch_id: Mapped[int] = mapped_column(ForeignKey("notice_batches.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("notice_drafts.id"))
    exit_case_id: Mapped[int] = mapped_column(ForeignKey("exit_cases.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    to_addresses: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(300))
    body_enc: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | queued | sent | delivered | bounced | failed | cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    ack_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_ts()


class Acknowledgement(Base):
    __tablename__ = "acknowledgements"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    message_id: Mapped[int] = mapped_column(ForeignKey("notice_messages.id"), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    acknowledged_at: Mapped[datetime] = created_ts()
    ip: Mapped[str | None] = mapped_column(String(64))


# --------------------------------------------------------------------------------------------
# Exit cases, FNF, documents, clearance, grievances
# --------------------------------------------------------------------------------------------

class ExitCase(Base):
    __tablename__ = "exit_cases"
    __table_args__ = (UniqueConstraint("plan_id", "employee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    state: Mapped[str] = mapped_column(String(30), default="identified")
    held_from_state: Mapped[str | None] = mapped_column(String(30))
    owner: Mapped[str] = mapped_column(String(200))
    selection_basis: Mapped[str] = mapped_column(String(20), default="algorithm")
    reason_code: Mapped[str | None] = mapped_column(String(30))
    reason_detail: Mapped[str | None] = mapped_column(Text)
    reason_version: Mapped[int] = mapped_column(Integer, default=0)
    reason_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    notice_date: Mapped[date | None] = mapped_column(Date)
    notice_days: Mapped[int | None] = mapped_column(Integer)
    pay_in_lieu: Mapped[bool] = mapped_column(Boolean, default=False)
    last_working_day: Mapped[date | None] = mapped_column(Date)
    lwd_trace: Mapped[dict | None] = mapped_column(JSON)
    actual_last_day: Mapped[date | None] = mapped_column(Date)
    hold_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hris_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExitTask(Base):
    __tablename__ = "exit_tasks"
    __table_args__ = (UniqueConstraint("exit_case_id", "auto_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int] = mapped_column(ForeignKey("exit_cases.id", ondelete="CASCADE"), index=True)
    auto_key: Mapped[str] = mapped_column(String(60))
    stage: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    owner_role: Mapped[str] = mapped_column(String(20))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | cancelled
    completed_by: Mapped[str | None] = mapped_column(String(200))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PayrollInput(Base):
    """Payroll data for FNF, one row per employee per period (YYYY-MM). Amounts in paise."""

    __tablename__ = "payroll_inputs"
    __table_args__ = (UniqueConstraint("employee_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="import")
    updated_by: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = created_ts()


class FnfStatement(Base):
    __tablename__ = "fnf_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int] = mapped_column(ForeignKey("exit_cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft | submitted | approved | rejected | superseded | paid
    pay_in_lieu: Mapped[bool] = mapped_column(Boolean, default=False)
    earnings_paise: Mapped[int] = mapped_column(BigInteger)
    deductions_paise: Mapped[int] = mapped_column(BigInteger)
    net_paise: Mapped[int] = mapped_column(BigInteger)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    ruleset_id: Mapped[int | None] = mapped_column(ForeignKey("rulesets.id"))
    needs_legal: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str] = mapped_column(String(64))
    computed_by: Mapped[str] = mapped_column(String(200))
    computed_at: Mapped[datetime] = created_ts()
    payment_due_on: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(100))


class FnfLine(Base):
    __tablename__ = "fnf_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    statement_id: Mapped[int] = mapped_column(ForeignKey("fnf_statements.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # earning | deduction
    component: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    rule_key: Mapped[str | None] = mapped_column(String(50))
    formula: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int | None] = mapped_column(ForeignKey("exit_cases.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[str] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    password_protected: Mapped[bool] = mapped_column(Boolean, default=False)
    issued_by: Mapped[str] = mapped_column(String(200))
    issued_at: Mapped[datetime] = created_ts()


class ClearanceItem(Base):
    __tablename__ = "clearance_items"
    __table_args__ = (UniqueConstraint("exit_case_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int] = mapped_column(ForeignKey("exit_cases.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(20))  # access | asset | handover | signoff
    key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    note: Mapped[str | None] = mapped_column(Text)
    owner_role: Mapped[str] = mapped_column(String(20))
    ticket_ref: Mapped[str | None] = mapped_column(String(100))
    updated_by: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Grievance(Base):
    __tablename__ = "grievances"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    exit_case_id: Mapped[int | None] = mapped_column(ForeignKey("exit_cases.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))  # process | reason | selection | fnf | other
    description_enc: Mapped[str] = mapped_column(Text)
    logged_by: Mapped[str] = mapped_column(String(200))
    logged_at: Mapped[datetime] = created_ts()
    ack_due_on: Mapped[date] = mapped_column(Date)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | under_review | decided | appealed | closed
    findings: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(20))  # upheld | partly_upheld | rejected
    outcome_reasons: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Appeal(Base):
    __tablename__ = "appeals"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    grievance_id: Mapped[int] = mapped_column(ForeignKey("grievances.id"), unique=True)
    grounds_enc: Mapped[str] = mapped_column(Text)
    filed_at: Mapped[datetime] = created_ts()
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | decided
    outcome: Mapped[str | None] = mapped_column(String(20))
    reasons: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------------------------
# Integrations, AI, queue, mail capture, audit
# --------------------------------------------------------------------------------------------

class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    type: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secrets_enc: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = created_ts()


class IntegrationRun(Base):
    __tablename__ = "integration_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    integration_id: Mapped[int] = mapped_column(ForeignKey("integrations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))  # running | succeeded | failed | needs_review
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = created_ts()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiDraft(Base):
    """LLM-written text for human review. Never read by scoring, selection, FNF or sending."""

    __tablename__ = "ai_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    exit_case_id: Mapped[int | None] = mapped_column(ForeignKey("exit_cases.id"), index=True)
    grievance_id: Mapped[int | None] = mapped_column(ForeignKey("grievances.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    kind: Mapped[str] = mapped_column(String(30))  # summary | explanation | notice | grievance_summary | reply
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()


class QueueJob(Base):
    __tablename__ = "queue_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    kind: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = created_ts()
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_ts()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapturedMail(Base):
    """Development mail capture: messages land here instead of being delivered."""

    __tablename__ = "captured_mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    to: Mapped[list] = mapped_column(JSON)
    subject: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = created_ts()


class AuditLog(Base):
    """Append-only and hash-chained per organisation. Guarded in the ORM and by DB triggers."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = org_fk()
    actor: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_ts()
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(50))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    justification: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(32))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


@event.listens_for(AuditLog, "before_update")
def _audit_no_update(*_):
    raise RuntimeError("audit_log is append-only")


@event.listens_for(AuditLog, "before_delete")
def _audit_no_delete(*_):
    raise RuntimeError("audit_log is append-only")
