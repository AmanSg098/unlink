// Thin client for the FastAPI backend. Requests go to /api/* and are proxied to the API by next.config.ts.

export type Role = "admin" | "hr" | "manager" | "legal" | "finance" | "approver" | "viewer";

export type Me = {
  kind: "staff" | "employee";
  id: number;
  email: string;
  full_name: string;
  role: Role | "employee";
  org_id: number;
  org_name: string;
  employee_code: string | null;
  mfa_required: boolean;
  mfa_verified: boolean;
  mfa_enabled: boolean;
  notify_email?: boolean;
};

export type LoginResult = {
  mfa_required: boolean;
  mfa_enrolled?: boolean;
  otpauth_uri?: string;
  secret?: string;
  qr_svg?: string;
};

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  active: boolean;
  employee_code: string | null;
  mfa_enabled: boolean;
  created_at: string;
};

export type Employee = {
  id: number;
  employee_code: string;
  full_name: string;
  email: string | null;
  personal_email: string | null;
  department: string;
  role: string;
  location: string;
  manager_code: string | null;
  hire_date: string;
  confirmation_date: string | null;
  employment_type: string;
  contract_end_date: string | null;
  contract_notice_days: number | null;
  status: string;
  annual_ctc_paise: number | null;
  salary_breakup: Record<string, number> | null;
  performance_rating: number;
  potential_rating: number;
  critical_skill_score: number;
  gender: string | null;
  age_band: string | null;
  leave_status: string | null;
  protected_flag: boolean | null;
  legal_hold: boolean | null;
  custom_metrics: Record<string, number> | null;
  protected: boolean;
  exclusion_reason: string | null;
  masked: string[];
};

export type EmployeeMeta = {
  total: number;
  hard_excluded: number;
  departments: string[];
  locations: string[];
  roles: string[];
  metrics: string[];
  by_status: Record<string, number>;
};

export type Factor = {
  key: string;
  label: string;
  description: string;
  higher_is_better: boolean;
  default_weight: number;
  custom: boolean;
  id: number | null;
  expression: string | null;
  created_by: string | null;
};

export type PlanStatus = "draft" | "submitted" | "approved";
export type SelectionMethod = "score_ranked" | "role_redundancy" | "manual_list";

export type Plan = {
  id: number;
  name: string;
  description: string;
  selection_method: SelectionMethod;
  target_count: number | null;
  target_cost_paise: number | null;
  filters: { departments: string[]; locations: string[]; roles: string[] };
  weights: Record<string, number>;
  eliminated_roles: string[];
  manual_codes: string[];
  as_of_date: string;
  status: PlanStatus;
  version: number;
  parent_plan_id: number | null;
  created_by: string;
  created_at: string;
  last_run_at: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_at: string | null;
  fairness_justification: string | null;
  kpi_snapshot: Record<string, { label: string; description: string; higher_is_better: boolean }> | null;
  ruleset: { id: number; title: string; version: string; unverified: number; total: number } | null;
  current_step: { step: string; roles: string[] } | null;
  cases: boolean;
};

export type PlanInput = Pick<
  Plan,
  "name" | "description" | "selection_method" | "target_count" | "target_cost_paise" | "filters" | "weights" |
  "eliminated_roles" | "manual_codes"
>;

export type Override = {
  id: number;
  employee_id: number;
  action: "include" | "exclude";
  justification: string;
  created_by: string;
  created_at: string;
};

export type ResultRow = {
  employee_id: number;
  employee_code: string;
  full_name: string;
  department: string;
  role: string;
  location: string;
  hire_date: string;
  annual_ctc_paise: number | null;
  score: number | null;
  rank: number | null;
  contributions: Record<string, number>;
  algo_selected: boolean;
  final_selected: boolean;
  excluded: boolean;
  exclusion_reason: string | null;
  override: Override | null;
  case: { id: number; state: string } | null;
};

export type Results = {
  summary: {
    pool: number;
    eligible: number;
    excluded: number;
    target: number | null;
    target_cost_paise: number | null;
    algo_selected: number;
    final_selected: number;
    overrides: number;
    annual_cost_reduction_paise: number | null;
  };
  rows: ResultRow[];
};

export type GroupStat = {
  group: string;
  pool: number;
  selected: number;
  selection_rate: number;
  retention_rate: number;
  impact_ratio: number | null;
  flagged: boolean;
  small_sample: boolean;
};

export type Fairness = {
  threshold: number;
  by_attribute: Record<string, GroupStat[]>;
  intersectional: GroupStat[];
  any_flagged: boolean;
  flags: string[];
  justification: string | null;
};

export type ComplianceCheck = { rule: string | null; severity: "info" | "warning" | "block"; message: string };

export type Approval = {
  id: number;
  entity_type: string;
  entity_id: number;
  round: number;
  step_index: number;
  step: string;
  roles: string[];
  status: "pending" | "approved" | "rejected" | "superseded" | "skipped";
  prepared_by: string;
  content_hash: string;
  decided_by: string | null;
  decided_at: string | null;
  comment: string | null;
  created_at: string;
  title?: string;
  link?: string;
};

export type AuditEntry = {
  id: number;
  actor: string;
  created_at: string;
  entity_type: string;
  entity_id: number | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  justification: string | null;
  request_id: string | null;
  hash: string;
};

export type AiDraft = {
  id: number;
  kind: string;
  employee_id: number | null;
  content: string;
  model: string;
  created_by: string;
  created_at: string;
  flagged_terms: string[];
};

export type KpiPreview = {
  count: number;
  errors: number;
  stats: { min: number; max: number; mean: number } | null;
  sample: { employee_code: string; value: number }[];
};

export type CaseState =
  | "identified" | "notice_drafted" | "notice_approved" | "notice_sent" | "notice_period" | "last_day_set"
  | "fnf_draft" | "fnf_approved" | "documents_issued" | "effective" | "closed" | "on_hold" | "withdrawn";

export type CaseSummary = {
  id: number;
  plan_id: number;
  plan_name: string;
  employee_id: number;
  employee: { id: number; employee_code: string; full_name: string; department: string; role: string;
    manager_code: string | null };
  state: CaseState;
  state_label: string;
  held_from_state: string | null;
  owner: string;
  selection_basis: string;
  reason_code: string | null;
  reason_detail: string | null;
  reason_version: number;
  notice_date: string | null;
  notice_days: number | null;
  pay_in_lieu: boolean;
  last_working_day: string | null;
  lwd_trace: { steps: { rule: string | null; step: string }[] } | null;
  actual_last_day: string | null;
  hold_reason: string | null;
  withdrawn_reason: string | null;
  open_tasks: number;
  overdue_tasks: number;
  created_at: string;
  effective_at: string | null;
  closed_at: string | null;
  hris_pushed_at: string | null;
};

export type Task = {
  id: number;
  exit_case_id: number;
  auto_key: string;
  stage: string;
  title: string;
  owner_role: string;
  due_date: string | null;
  status: "open" | "done" | "cancelled";
  completed_by: string | null;
  employee_code?: string;
  overdue?: boolean;
};

export type Evidence = {
  id: number;
  entity_type: string;
  entity_id: number;
  evidence_type: string;
  filename: string;
  content_type: string;
  size: number;
  sha256: string;
  scan_status: string;
  uploaded_by: string;
  uploaded_at: string;
};

export type NoticeMessage = {
  id: number;
  batch_id: number;
  draft_id: number;
  exit_case_id: number;
  is_test: boolean;
  excluded: boolean;
  to_addresses: string[];
  subject: string;
  content_hash: string;
  status: string;
  attempts: number;
  last_error: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  acknowledged_at?: string | null;
  acknowledged?: boolean;
  employee_code?: string;
  full_name?: string;
  body?: string;
};

export type FnfLine = {
  id: number;
  position: number;
  kind: "earning" | "deduction";
  component: string;
  label: string;
  amount_paise: number;
  rule_key: string | null;
  formula: string;
  inputs: Record<string, unknown>;
};

export type FnfStatement = {
  id: number;
  exit_case_id: number;
  version: number;
  status: string;
  pay_in_lieu: boolean;
  earnings_paise: number;
  deductions_paise: number;
  net_paise: number;
  inputs: Record<string, unknown>;
  needs_legal: boolean;
  content_hash: string;
  computed_by: string;
  computed_at: string;
  payment_due_on: string | null;
  paid_at: string | null;
  payment_reference: string | null;
  employee?: { employee_code: string; full_name: string; department: string };
  case_state?: string;
  current_step?: { step: string; roles: string[] } | null;
  lines?: FnfLine[];
  approvals?: Approval[];
};

export type Doc = {
  id: number;
  kind: string;
  version: number;
  title: string;
  sha256: string;
  password_protected: boolean;
  issued_by: string;
  issued_at: string;
};

export type ClearanceItem = {
  id: number;
  category: "access" | "asset" | "handover" | "signoff";
  key: string;
  label: string;
  status: string;
  note: string | null;
  owner_role: string;
  ticket_ref: string | null;
  updated_by: string | null;
};

export type Grievance = {
  id: number;
  ref: string;
  exit_case_id: number | null;
  employee_id: number;
  employee: { employee_code: string; full_name: string };
  category: string;
  logged_by: string;
  logged_at: string;
  ack_due_on: string;
  acknowledged_at: string | null;
  status: string;
  findings: string | null;
  outcome: string | null;
  outcome_reasons: string | null;
  decided_by: string | null;
  decided_at: string | null;
  case_state: string | null;
  description?: string;
  appeal: { id: number; status: string; outcome: string | null; reasons: string | null; decided_by: string | null;
    grounds?: string } | null;
};

export type Template = {
  id: number;
  key: string;
  type: string;
  title: string;
  subject: string;
  body: string;
  version: number;
  status: "draft" | "legal_approved" | "retired";
  send_to_personal: boolean;
  attach_pdf: boolean;
  encrypt_attachment: boolean;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  merge_fields: string[];
};

export type Draft = {
  id: number;
  exit_case_id: number;
  template_id: number;
  version: number;
  subject: string;
  body: string | null;
  missing_fields: string[];
  flagged_terms: string[];
  content_hash: string;
  status: string;
  created_by: string;
  created_at: string;
  employee_code: string;
  full_name: string;
  template: { id: number; title: string; version: number; status: string; type: string };
};

export type Batch = {
  id: number;
  name: string;
  status: "draft" | "pending_approval" | "approved" | "released" | "completed";
  created_by: string;
  created_at: string;
  test_sent_at: string | null;
  released_by: string | null;
  released_at: string | null;
  counts: Record<string, number>;
  problems: string[];
  current_step: { step: string; roles: string[] } | null;
  approvals: Approval[];
  messages?: NoticeMessage[];
};

export type Notification = { id: number; kind: string; title: string; link: string | null; read_at: string | null;
  created_at: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function errorDetail(body: unknown): string {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => `${e.loc?.slice(1).join(".")}: ${e.msg}`).join("; ");
  return "Request failed";
}

export const UNAUTHORIZED_EVENT = "unlink:unauthorized";

/** Calls the API with the session cookie. A 401 fires UNAUTHORIZED_EVENT (handled by AuthProvider). */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, cache: "no-store", credentials: "same-origin" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(res.status, errorDetail(body));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const patch = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const upload = <T>(path: string, fields: Record<string, string>, file: File) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  fd.append("file", file);
  return api<T>(path, { method: "POST", body: fd });
};

export const fmtMoney = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

/** Money is stored in paise; show rupees. */
export const fmtPaise = (p: number | null | undefined, digits = 0) =>
  p === null || p === undefined ? "–" :
    new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: digits,
      minimumFractionDigits: digits }).format(p / 100);

export const fmtDay = (iso: string | null | undefined) =>
  iso ? new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-IN",
    { day: "numeric", month: "short", year: "numeric" }) : "–";
