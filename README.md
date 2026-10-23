# Unlink

**Plan, communicate and close out workforce reductions: fairly, lawfully, and on record. Every step that affects a person is approved by a human first.**

Unlink is an HR operations platform for organisations that need to reduce headcount or exit individual employees. It covers the full cycle:

1. **Track performance** continuously, so decisions rest on documented evidence.
2. **Plan** a reduction with explainable, deterministic selection and a fairness check.
3. **Notify** affected employees with personalised, reviewed letters and track delivery and acknowledgement.
4. **Record reasons** in a structured form tied to evidence.
5. **Close out** each exit: notice handling, full and final settlement (FNF), documents, and access revocation.
6. **Prove it** with an append-only audit trail and a defensibility pack.

> **Status:** working development build. All legal content (the India ruleset, notice templates, reason wording and the protected-terms list) is a **placeholder that no lawyer has verified**. Don't use it with real employees. See [Implementation status](#implementation-status) for what is built and what is still a stub.

## What Unlink does and does not do

**It does:**
- Track goals, check-ins, reviews, ratings and performance improvement plans (PIPs) as the evidence base for decisions.
- Score and rank people with transparent weighted arithmetic. AI is never in this path.
- Draft and send notices and letters to employees, but only after a human has reviewed each one.
- Calculate FNF components from payroll inputs, with a line-by-line statement that shows the rule behind each number.
- Run per-employee exit cases through a fixed set of stages, each with an owner and due date.
- Keep an immutable record of every decision, override, email, and approval.

**It does not:**
- Send anything to an employee without a human approving that specific message at the send step.
- Terminate an employee in an HRIS or payroll system on its own. Pushing an exit to an external system is a separate, explicitly approved action.
- Let AI make, recommend, or alter any selection, rating, or amount.
- Use gender, age, caste, religion, or health/leave data in scoring. Those fields are used only for fairness analysis and protected-status checks.
- Provide legal advice. Jurisdiction rules are configuration, marked "unverified" until a qualified lawyer signs them off.

## Core principles

1. **Human approval gates.** Each irreversible step (sending a notice, locking a selection, approving an FNF, marking an exit effective) needs a named approver who is not the person who prepared it.
2. **Evidence before action.** A termination reason must link to recorded evidence (review, PIP outcome, redundancy approval, and so on). A free-text reason alone is not accepted.
3. **Protected people are excluded by rule.** Maternity, medical leave, protected-status flags, and other configured protections block selection and exit. No weight, filter, or manual override can bypass them.
4. **Dry run before live.** Every communication batch can be previewed, test-sent to internal addresses, and then released.
5. **Nothing is silently changed.** Edits to approved items create a new version and reopen approval.
6. **Least data.** Employees see only their own case. Sensitive fields are masked by role.

---

## Contents

1. [Quick start](#quick-start)
2. [Roles and permissions](#roles-and-permissions)
3. [Lifecycle overview](#lifecycle-overview)
4. [Modules](#modules)
5. [Web app](#web-app)
6. [Architecture](#architecture)
7. [Data model](#data-model)
8. [API reference](#api-reference)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Development guide](#development-guide)
12. [Implementation status](#implementation-status)
13. [Decisions taken](#decisions-taken)
14. [Limitations](#limitations)

---

## Quick start

### Prerequisites

| Tool | Used for |
|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | API and worker |
| Node.js 20+ and npm | Web app |
| Homebrew `pango` (macOS) | PDF generation (installed by `setup.sh`) |

No Docker and no Redis are needed. The default database is SQLite, and the worker queue lives in the same database.

### Commands

```bash
./setup.sh   # once: dependencies, migrations, demo data, Playwright browser
./dev.sh     # API, worker, mail viewer and web app (Ctrl+C stops all)
./test.sh    # all test suites
```

- **Web app:** http://localhost:3100
- **API docs:** http://localhost:8000/docs
- **Mail viewer (development):** http://localhost:8025. Outgoing mail is captured in the database and shown here; it is never delivered.

### Demo accounts

Password for all demo accounts: **`unlink-demo`** (development only).

| Email | Role | Organisation | MFA |
|---|---|---|---|
| `admin@democorp.in` | Admin | Demo Corp | required |
| `hr@democorp.in` | HR Operations | Demo Corp | |
| `manager@democorp.in` | Manager (head of Support) | Demo Corp | |
| `legal@democorp.in` | Legal | Demo Corp | required |
| `finance@democorp.in` | Finance | Demo Corp | required |
| `approver@democorp.in` | Approver | Demo Corp | required |
| `viewer@democorp.in` | Viewer | Demo Corp | |
| `admin@acme.in` | Admin | Acme Pvt Ltd (empty, for isolation tests) | required |

**MFA in development:** the first sign-in for an MFA role shows a QR code to enrol in any authenticator app. To skip the phone, the sign-in page has demo-account buttons that complete MFA automatically, and a "Fill the current code" link. Both use `GET /api/dev/totp`, which exists only when `APP_ENV=development`.

Demo Corp is seeded with **250 synthetic employees**, four closed review cycles (979 reviews), sample goals, check-ins and PIPs, a sample jurisdiction ruleset (India, unverified), nine notice templates (draft), and sample payroll inputs. No real personal data is used.

### Configuration for live email

Development never sends mail. For staging or production, set `APP_ENV`, `MAIL_PROVIDER` and its credentials (see [Configuration](#configuration)). Live sending is refused unless `APP_ENV` is `staging` or `production`.

---

## Roles and permissions

| Action | Viewer | Manager | HR Ops | Legal | Finance | Approver | Admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| View plans, results, fairness, own team's performance | ✓ | own team | ✓ | ✓ | ✓ | ✓ | ✓ |
| Record goals, check-ins, reviews | | own team | ✓ | | | | ✓ |
| Start / close a PIP | | propose | ✓ | ✓ | | | ✓ |
| Create and run reduction plans | | | ✓ | | | | ✓ |
| Add / revoke overrides | | | ✓ | | | | ✓ |
| Submit a plan for approval | | | ✓ | | | | ✓ |
| Approve / reject a plan step | | | | ✓ | ✓ | ✓ | ✓ |
| Draft notices and letters | | | ✓ | ✓ | | | ✓ |
| Approve a notice batch for sending | | | | ✓ | | ✓ | ✓ |
| Send an approved batch | | | ✓ | | | | ✓ |
| Create exit cases | | | ✓ | | | | ✓ |
| Compute and submit FNF | | | ✓ | | ✓ | | ✓ |
| Approve FNF | | | | ✓ | ✓ | | ✓ |
| Mark an exit effective | | | ✓ | | | ✓ | ✓ |
| Push an exit to an external HRIS/payroll | | | | | ✓ | | ✓ |
| Manage jurisdiction rulesets | | | | ✓ | | | ✓ |
| Log grievances, record appeal outcomes | | | ✓ | ✓ | | | ✓ |
| Manage users and integrations | | | | | | | ✓ |

**Separation of duties (enforced by the server, not the UI):**
- Whoever prepared an item can never approve it.
- The person who drafted a notice can't approve its send.
- The person who computed an FNF can't approve it.
- One person can't approve two steps of the same approval round.
- An approver can't approve an exit for a case they own or for someone in their reporting line.
- A grievance can't be decided by the case owner or the person who logged it, and an appeal can't be decided by whoever took the original decision.
- Managers see only their own reporting line, and never see other managers' private check-in notes.

---

## Lifecycle overview

Each employee in a reduction moves through an **exit case**. Each reduction plan has a set of cases, one per selected employee.

```
PERFORMANCE          PLANNING                 NOTIFICATION               EXIT
(continuous)         (reduction plan)         (per employee)             (per employee)

goals, check-ins  →  scope, criteria,     →  draft notice         →  notice period (if any)
reviews, PIPs        scoring, fairness       reason + evidence          │
                     legal + approval        legal review               ▼
                          │                  approve batch              last working day
                          ▼                  send (dry run first)       │
                     plan approved  ───────▶ delivery + acknowledgement ▼
                                                                     FNF computed → approved
                                                                         │
                                                                         ▼
                                                                     documents issued
                                                                     access revoked
                                                                     exit marked effective
                                                                         │
                                                                         ▼
                                                                     closed (audit sealed)
```

**Exit case states:** `identified` → `notice_drafted` → `notice_approved` → `notice_sent` → `notice_period` → `last_day_set` → `fnf_draft` → `fnf_approved` → `documents_issued` → `effective` → `closed`. Cases can also be `on_hold` (grievance, legal hold) or `withdrawn` (with a reason). Each transition is audited and some require an approval. The state machine is in `apps/api/app/exits/states.py`.

---

## Modules

### Organisations and sign-in

- Email and password, hashed with **scrypt**. Sessions use a random token (only its SHA-256 hash is stored) in an **httpOnly, SameSite=Lax** cookie (`unlink_session`). Sessions last **12 hours** and can be ended from **My account**.
- **Multi-factor authentication (TOTP)** is required for Legal, Finance, Approver and Admin. Enrolment shows a QR code on first sign-in; the secret is stored encrypted. An admin can reset a user's MFA.
- Failed logins are rate-limited: 5 failures per account or 20 per IP in 15 minutes. Login errors don't reveal whether an email exists.
- SSO (SAML/OIDC) is a roadmap item.
- Every table except `orgs` carries `org_id`. Every query is scoped to the signed-in user's organisation; other organisations' records return 404.
- Deactivating a user ends their sessions immediately.

### People

Each employee record includes:

| Field | Notes |
|---|---|
| `employee_code` | Unique per organisation. Used everywhere outside HR screens. |
| `full_name`, `email`, `personal_email` | `personal_email` is used for exit communications when the work account is closed |
| `department`, `role`, `location`, `manager_code` | `manager_code` drives the reporting line |
| `hire_date`, `confirmation_date` | Tenure and notice eligibility are based on these |
| `employment_type` | `permanent`, `contract`, `fixed_term`, `intern` (used by rules); `contract_end_date`, `contract_notice_days` |
| `annual_ctc_paise`, `salary_breakup` | Annual CTC in integer paise. Used for cost, notice pay and FNF |
| `performance_rating`, `potential_rating`, `critical_skill_score` | 1–5, sourced from the performance tracker or import |
| `gender`, `age_band` | **Fairness analysis only** |
| `leave_status` | `none`, `maternity`, `medical`, `other`. Protected while active. |
| `protected_flag`, `legal_hold` | Manual protection (for example, pending a complaint) |
| `custom_metrics` | Imported `kpi_<name>` values |
| `status` | `active`, `on_notice`, `exited`, `on_hold` |

Pay fields are visible only to HR, Finance and Legal; gender, age band and leave status only to HR and Legal. Other roles see them as "masked". Every change writes an `employee_history` row and an audit entry.

**CSV import** (People → People CSV): required columns `employee_code, full_name, department, role, location, hire_date, annual_ctc, performance_rating, potential_rating, critical_skill_score, gender, age_band`; optional `email, personal_email, manager_code, employment_type, confirmation_date, contract_end_date, contract_notice_days, leave_status, protected_flag` and `kpi_<name>` columns. Money is given in rupees and stored in paise. Rows are upserted by `employee_code`. Errors are reported by line number only. Every import is audited with created, updated and error counts.

**Payroll CSV** (People → Payroll CSV): `employee_code, period (YYYY-MM)`, monthly `basic, da, hra, special` in rupees, and FNF inputs such as `leave_encashable_days`, `reimbursements_approved`, `loans_outstanding`, `tds`.

**HRIS sync:** a manual pull from a connected HRIS CSV drop (see [Integrations](#integrations)) updates the same fields. Conflicts are shown for review rather than overwritten.

### Performance tracker

The performance tracker is the evidence base for selection and for reasons. It runs continuously, not only at review time.

**Goals**
- HR or the manager sets goals per employee for a cycle: title, description, weight, target, due date, and an optional team objective.
- Progress is recorded as a percentage with a dated note.

**Check-ins**
- One-to-ones with a summary, a sentiment tag, and action items with owners and due dates.
- Manager-only private notes are stored encrypted and separately; HR and other managers never see them.

**Review cycles**
- Cycles have a name, period, and rating scale (default 1–5).
- Each review has a self-assessment, a manager rating, an optional peer input, and a calibrated final rating.
- Calibration shows the distribution per department and flags outliers. Closing a cycle makes the calibrated rating the employee's `performance_rating`.
- Ratings history is kept per cycle and used for the "last three cycles" trend factor.

**Feedback**
- Structured feedback (strength, improvement area, example, date) linked to the employee and the author. Authors are visible to HR; whether employees see them is an organisation setting.

**Performance improvement plans (PIPs)**
- A PIP has: reason category, the specific performance gaps, measurable success criteria, start and end dates (default 60 days), named support, and check-in dates.
- Each milestone records the evidence reviewed and the outcome (`met`, `partially_met`, `not_met`). Entries are signed by the manager and acknowledged by the employee, or marked "employee declined to sign" with the date.
- A PIP can't be closed as "not met" without at least two dated check-ins and a documented final review.
- PIP status feeds the `pip_status` factor and is required evidence for the `PERF-PIP` reason code.

**Evidence attachments**
- Files (review forms, emails, incident notes) can be attached to performance records and exit cases. Uploads are checked against an extension allow-list and magic bytes, size-limited (`MAX_UPLOAD_BYTES`), optionally virus-scanned through ClamAV (`CLAMD_SOCKET`), and stored encrypted with AES-256-GCM. Access follows the record's visibility rules.

**Reports**
- Per-employee performance history (on the profile), PIP pipeline, calibration per cycle, and a **missing evidence** report: people with a low rating but no documented review or PIP.

### KPI library and custom KPIs

**Built-in factors** (used in selection scoring), defined in `apps/api/app/kpi/library.py`:

| Key | Factor | Direction | Default weight |
|---|---|---|---|
| `performance` | Calibrated performance rating (last cycle) | Higher is better | 35% |
| `performance_trend` | Average of the last three cycles | Higher is better | 10% |
| `potential` | Assessed potential | Higher is better | 15% |
| `skill_criticality` | Criticality of skills | Higher is better | 20% |
| `tenure` | Years of service at the data-as-of date | Higher is better | 10% |
| `pip_status` | Active or recently closed PIP | Penalty if active | 10% |
| `cost` | Annual CTC | **Lower is better** | 0% |

`pip_status` maps to a value in [0, 1]: no PIP = 1, closed with success = 1, partially met = 0.5, active = 0.25, not met = 0. The mapping can be overridden per organisation (`settings.pip_status_map`).

**Custom KPIs** are formulas parsed to a syntax tree and checked against an allow-list, with no `eval`. They can use performance fields, `metric("name", default)` for imported values, and `min`, `max`, `abs`, `round`, `floor`, `ceil`, `clamp`. Formulas can be previewed across the whole organisation before saving, and archived later.

Each plan stores a snapshot of the factor definitions it used, so the report still explains an old plan after a KPI changes.

### Reduction plans (scenarios)

A plan is one proposed reduction:

- **Name**, **business rationale**, and **target**: headcount, a cost-saving figure, or both.
- **Scope**: departments, locations and roles. Empty means the whole organisation.
- **Selection method:** `score_ranked` (default, see [Selection scoring](#selection-scoring)), `role_redundancy` (everyone in the eliminated roles, minus exclusions), or `manual_list` (HR supplies employee codes, which are then checked against every rule).
- **Weights**, **data-as-of date**, and the **ruleset version** in force.
- **Statuses:** draft → submitted → approved (a rejection returns the plan to draft). Approval is a prerequisite for creating exit cases.

Only draft plans can be edited or re-run. Approved plans are immutable; any change needs a new version (`POST /plans/{id}/new-version`) and fresh approval.

### Selection scoring

1. For each **eligible** person in scope, normalise each factor across the eligible pool to 0–1 (min-max). If everyone has the same value, the value is 0.5.
2. Flip "lower is better" factors (cost).
3. Score = 100 × Σ(weight × normalised value), with weights rescaled to sum to 1.
4. Sort by score ascending. Ties break on employee ID, so results are reproducible.
5. The first *target* people are **proposed**. With a cost target, people are proposed in rank order until the saving is reached.

**Hard exclusions**, applied before scoring and not overridable (`apps/api/app/scoring/exclusions.py`):
- Maternity or medical leave in progress.
- Protected flag set, or legal hold.
- Anyone with an open grievance.
- Anyone whose PIP is active and within its end date (they are "on track", not "proposed").
- Anyone whose notice period has already started under an earlier plan, or who has already exited.

Excluded people are listed with the reason and never scored. HR can override the proposed list (include or exclude, with a written justification), but never for a hard-excluded person.

**Explainability:** every person's score is broken into per-factor contributions in points, and the plan report explains the method in plain language.

### Fairness check

- **Attributes:** gender, age band, department, location, employment type, and tenure band.
- **Four-fifths rule** on retention rates, with the impact ratio shown per group. Groups under 5 people are shown as small samples and not flagged.
- **Intersectional view:** gender × age band, shown only where the group has at least 5 people.
- **Blocking gate:** a flagged plan can't be approved at the final step unless the approver records a written justification, which goes into the audit log and the defensibility pack.

This is a screening aid for human review, not a legal determination.

### Reason codes and evidence

Every exit needs a **reason code** from a fixed list (`apps/api/app/reasons/__init__.py`). Free text can add detail but can't replace the code.

| Code | Name | Required evidence |
|---|---|---|
| `RED-ROLE` | Role eliminated | Approved role-elimination record |
| `RED-TEAM` | Team or unit restructured | Approved restructuring record |
| `RED-LOC` | Location closed or consolidated | Location decision record |
| `PERF-PIP` | Performance not improved after PIP | Closed PIP with recorded outcome and final review |
| `PERF-REVIEW` | Performance below standard (no PIP) | Review cycles with ratings below the configured threshold |
| `CONDUCT` | Conduct (policy breach) | Investigation outcome record |
| `ATTEND` | Attendance | Attendance record and any prior warnings |
| `VOLUNTARY` | Voluntary separation or buyout | Signed acceptance |
| `CONTRACT-END` | Fixed-term or contract end | Contract end date |
| `OTHER` | Other (legal review required) | Written justification approved by Legal |

Rules enforced by the system:
- A reason can't be used on a notice until its required evidence is linked. The case page shows each evidence item as present or missing.
- Reason text can't cite protected characteristics or leave status. Terms from `apps/api/app/reasons/protected_terms.yaml` (pregnancy, disability, religion, …) are blocked in reason text and flagged in notice drafts and AI drafts.
- The wording shown to the employee comes from the code's approved wording template, which Legal approves before first use (`/rules` → Reason codes).
- The reason is stored once per case, versioned, and linked to the plan and the notice.

### Notices and communications

**Templates** (`templates/notices/*.md`, front matter + body)
- Each template has a type, subject, body with `{{ merge_fields }}`, a jurisdiction tag, a version, and a status (`draft`, `legal_approved`, `retired`).
- Types: pre-notice consultation, notice of termination, notice of role elimination, PIP outcome, FNF statement cover, relieving letter cover, experience letter cover, grievance acknowledgement, appeal outcome.
- Only `legal_approved` templates can be used to send; drafts can be previewed. Editing an approved template creates a new draft version.
- Merge fields are checked when drafting. Missing fields show as `[MISSING: field]` and block the batch.

**Drafting**
- A draft is generated per employee from the template, the employee's data, the case's reason wording, and the dates computed from the ruleset.
- HR can edit the text; each edit is a new version, and any batch containing it returns to draft.

**Review and approval**
- Notices are approved as a batch, but each message has its own preview. The approver can exclude individual messages.
- Approval is bound to the exact content hash of every message, so any later edit requires a new approval.

**Sending**
- **Dry run first:** a test send goes to internal test addresses (org setting), marked "TEST" in the subject and body.
- **Release:** an approved batch is queued and the worker sends it in throttled chunks (`MAIL_RATE_PER_MINUTE`, default 20), with retries and backoff on temporary failure. Release re-checks the approval hash, that the notice date hasn't passed, and the consultation sequence from the ruleset.
- Messages go to the work email, and also to the personal email when the template requires it.
- **Attachments:** letters are rendered to PDF, watermarked "CONFIDENTIAL", and, if the template requires it, encrypted (AES-256) with a password sent in a separate email.

**Tracking**
- Delivery status per message: queued, sent, delivered, bounced, failed.
- Acknowledgement: employees confirm receipt through a link (`/ack/<token>`) or in self-service. The acknowledgement records time and IP only.
- Bounces create a task and a notification for HR to fix the contact details; the resend is audited.
- Message history is append-only. Message bodies are stored encrypted.

**Consultation and notice periods** are configured in the ruleset. Unlink creates the consultation tasks and blocks a release that would breach the configured sequence.

### Exit cases

One case per employee per plan, created from an approved plan.

- **Case record:** employee, plan, reason code and evidence, selection basis (algorithm or override), notice dates, last working day, owner, and state.
- **Tasks:** each stage creates tasks with an owner role and due date (for example "confirm bank details for FNF", "issue relieving letter"). Overdue tasks show on the dashboard and in the weekly report.
- **Notice period:** computed from the ruleset and the employee's contract, with the option to pay in lieu of notice. The last working day is shown with each rule that produced it.
- **Notice shortfall:** if the actual last day is earlier, the shortfall days are calculated and flow into FNF as a recovery where the rules allow it.
- **Holds:** Legal or HR can put a case on hold (grievance, investigation). A hold freezes dates and blocks termination notices, FNF and exit steps (HTTP 423). Grievance acknowledgements still go out.
- **Withdrawal:** a case can be withdrawn with a reason. Withdrawal is audited and cancels any notices not yet sent.
- **Mark effective** needs an approver; **push to HRIS** needs Finance approval and writes `exits.csv` to the HRIS drop folder.

### Notice periods and jurisdiction rules

Rules are stored as versioned YAML files in `rules/`. Each rule has `id`, `title`, `jurisdiction`, `applies_to` (employment type, establishment size, tenure), `value` (a value or formula in the same safe expression language as custom KPIs), `source` (statute or policy, with section), `effective_date`, and `verified_by` (name and date of the reviewing lawyer), empty until verified.

The **shipped India ruleset (`rules/india/2026.1.yaml`, 21 rules) is a placeholder** for development. Every rule shows **"Unverified: not for use with real employees"** until counsel verifies it through `/rules`, and a banner appears on every plan that uses unverified rules. With `RULESET_MODE=production`, plans can't be approved while they use unverified rules (HTTP 423).

The ruleset covers statutory notice periods and notice to government by establishment size, retrenchment compensation (formula, minimum service, cap), order of retrenchment (last come, first go), gratuity, leave encashment, bonus proration, FNF payment timing, consultation and notice sequencing, protected categories, PIP length, grievance acknowledgement days, and a state-level variation example.

Each plan records the ruleset version it used, so old plans always show the rules they were built on.

### Full and final settlement (FNF)

**Inputs** come from the payroll import or manual entry per employee: basic and allowances, days worked in the final month, leave balance, gratuity inputs, notice pay (paid or recovered), bonus due, reimbursements, loans, advances and recoveries, and TDS.

**Calculation** (`apps/api/app/fnf/`):
- Each component is computed by a named function that reads the ruleset and cites the rule ID.
- The statement lists every earning and deduction with the rule, the formula, and the inputs used.
- All money is integer paise, computed with `Decimal`; the net is rounded to the rupee as the ruleset specifies.
- A **what-if** view compares, for example, paying notice versus working it out.

**Workflow:**
1. HR or Finance computes the FNF draft from the case.
2. Finance reviews it against payroll and approves (the person who computed it can't).
3. Legal reviews as a second step when the statement includes compensation or gratuity.
4. Approval locks the statement; recomputing creates a new version that needs approval again.
5. Approved statements are exported as CSV for payroll and issued as a PDF document, sent with the FNF cover template through the normal batch review.
6. Payment is recorded with a reference. Unlink does not move money.

**Not included:** tax filing, statutory returns, and provident fund transfers.

### Documents

Generated from `templates/documents/`, versioned and stored encrypted with their hash: termination or retrenchment letter, role elimination notice, FNF statement, relieving letter (issued only after clearance or an approved exception), experience letter, certificate of service, and acknowledgement form.

Documents are rendered to PDF with WeasyPrint, watermarked, and sealed with a SHA-256 hash recorded in the audit log. The case shows which version was issued, by whom and when.

### Access and asset clearance

Each case gets a checklist when the notice is sent:

- **Access revocation:** email, VPN, internal apps, building access: `requested` → `revoked` → `verified`. With a ticketing webhook configured, a ticket is raised for each request; otherwise it stays a task.
- **Asset return:** laptop, phone, access card, documents, each with a status and condition note.
- **Handover:** a manager note on work handover and ownership changes.
- **Sign-off** by the manager, IT and HR. The relieving letter is blocked until clearance is complete, or an approver records an exception.

### Grievances and appeals

- **Intake:** HR logs a grievance, or the employee logs one in self-service. Grievances about the process, reason, or selection put the case on hold automatically.
- **Acknowledgement:** an acknowledgement draft and a one-message batch are prepared immediately from the grievance acknowledgement template, and must be sent within the ruleset's deadline (shown on the grievance).
- **Review:** HR and Legal record findings and the outcome (upheld, partly upheld, rejected) with reasons.
- **Appeal:** the employee can appeal once. The appeal is decided by someone other than the original decider.

### Approvals

One approval engine (`apps/api/app/workflow/`) serves plans, notice batches, FNF, templates, reason wording, "Other" reasons, clearance exceptions, exit effective, and HRIS pushes. Default sequences (`workflow/sequences.py`):

| Item | Steps |
|---|---|
| Plan | Legal review → Finance review → Final approval (Approver) |
| Notice batch | Approve for sending (Legal or Approver) |
| FNF | Finance review → Legal review (only for compensation or gratuity) |
| Template | Legal approval |
| "Other" reason | Legal approval |
| Clearance exception | Approver |
| Exit effective | Approver |
| HRIS push | Finance |

- Each step records the approver, time, decision and comment. Rejection requires a comment and returns the item to draft.
- Approval is bound to a content hash. Any change after approval invalidates it.
- Approvers get in-app notifications and email. Items pending longer than the org's `escalation_days` (default 3) are escalated to admins once.

### Reports and exports

**Defensibility pack** (PDF, per plan, `/plans/{id}/report.pdf`): organisation and plan details, rationale and approval history; method (scope, criteria, weights, ruleset version and verification status); fairness tables and flags with the justification; selected people by reason code (names in the internal copy, removed with `?external=true`); protected counts by reason (no names); override log; communication log; FNF totals by component; and an audit trail excerpt.

**Per-employee exit file** (PDF): case summary, reason and evidence, notices with timestamps, FNF statement, documents issued, clearance, and grievances.

**Exports:** plan CSV, FNF payroll CSV, HRIS exits CSV, and a JSON export of the audit trail.

**Scheduled reports:** a weekly summary of open cases, overdue tasks, pending approvals and bounced notices, emailed to HR (counts and links only).

### AI drafting

AI drafts text. It never decides, scores, selects, or sends.

**Available drafts:**
- Executive summary of a plan for the approval committee
- Plain-language explanation of a person's ranking (shown next to the exact factor contributions)
- First draft of a notice from the template and reason wording (must still be edited, reviewed and approved)
- Summary of a grievance for the reviewer
- Draft replies to employee questions, for HR to edit

**Guarantees:**
- Drafts are labelled "AI draft · review before use" and stored separately (`ai_drafts`).
- The model never receives names, salaries, gender, age, leave or health details. Employee codes and role-level facts are used instead, and free text is redacted before it is sent.
- Generated notice text is checked against the protected-terms list.
- A test fails if scoring, fairness, workflow, FNF, or sending code imports the AI module.
- The audit log records the draft event, the author and the model, not the text.
- Without `ANTHROPIC_API_KEY`, AI endpoints return 503 and the rest of the app works normally.

**Model:** Claude Opus 5.5 (`claude-opus-5-5`), set in `apps/api/app/ai/drafting.py`.

### Audit log

Every state change, approval, send, and reveal of sensitive data is recorded with actor, time, entity, action, before and after values, justification, and the request ID (also returned as the `X-Request-ID` header).

**Covered:** plans, overrides, approvals, templates, notice batches (with each message's content hash), sends, deliveries, acknowledgements, FNF inputs and outputs, documents, clearance, grievances and appeals, performance records, PIP entries, imports, user changes, data exports and pseudonymisation, and sensitive views such as opening an FNF statement.

**Properties:**
- **Append-only**, enforced in the ORM and by database triggers on SQLite and PostgreSQL.
- **Hash-chained** per organisation: each entry stores the hash of the previous one. `GET /api/audit/verify` (or `uv run python -m app.cli verify-audit`) checks the chain and reports the first broken entry.
- **Viewable** by Legal and Admin on `/audit`; each case, plan and grievance also shows its own trail.

### Integrations

Each integration is off by default and enabled per organisation by an Admin on `/integrations`. Secrets are encrypted at rest and never shown again after entry.

| Type | Implemented now | Planned |
|---|---|---|
| HRIS | CSV drop folder: pull people (conflicts held for review), write exits after approval | Keka, Darwinbox, greytHR APIs |
| Payroll | CSV import of FNF inputs, CSV export of approved FNF | Payroll APIs |
| Email | Capture (development), SMTP, Amazon SES via SMTP | SendGrid |
| Ticketing | Generic webhook (one ticket per access revocation) | Jira, ServiceNow, Freshdesk |
| Messaging | Slack and Microsoft Teams incoming webhooks | |
| E-signature | | Optional provider |
| SSO | | SAML, OIDC |

### Notifications

- **In-app** (bell): tasks, approvals, escalations, grievance deadlines, bounced messages.
- **Email to staff:** approval requests, reminders and escalations to the relevant people only. Notification emails contain no employee names or amounts; they link to the item. Each user can turn these off on **My account**.
- **Messaging integrations:** optional, with the same content rules.

### Privacy, retention and security

- **Application logs** contain IDs and counts only. Names, pay, ratings and leave data never appear in logs or error messages (a test checks this).
- **Encryption:** AES-256-GCM at rest for sensitive fields (`*_enc`), letters, attachments and message bodies, with a key derived from `SECRET_KEY`. Use TLS in front of the app in any shared environment.
- **Access:** field-level masking by role; sensitive views are audited.
- **Retention:** per-organisation periods (defaults: plans and audit log 7 years; closed-case personal data 3 years after exit, then pseudonymised; rejected-plan drafts 1 year). A daily worker job applies them. Legal hold blocks pseudonymisation.
- **Data subject rights:** export a person's data as JSON and pseudonymise it from their profile. Both are audited.
- **Data processing:** designed to support obligations under India's Digital Personal Data Protection Act, 2023. Legal to confirm.
- **Before production:** encrypted backups, least-privilege database roles, dependency scanning, a secrets manager or KMS, and a penetration test.

---

## Web app

| Route | Page | Who | What's there |
|---|---|---|---|
| `/` | Landing | Public | Product overview and safeguards |
| `/login` | Sign in | Public | Email/password, MFA enrolment and prompt |
| `/dashboard` | Home | All staff | Alerts (unverified rules, bounces, overdue items), approvals waiting for you, tasks due, cases by stage, recent plans |
| `/people` | People | HR, Manager (own team), others read-only | Searchable table, filters, people and payroll CSV import, add |
| `/people/[code]` | Employee profile | By role | Details (masked by role), payroll, performance history, goals, check-ins, PIPs, evidence, exit cases, history, data export |
| `/performance` | Performance | HR, Manager, Legal | Overview, review cycles, PIP pipeline, missing-evidence report |
| `/performance/cycles/[id]` | Review cycle | HR | Reviews, calibration, distribution and outliers |
| `/kpis` | KPI library | HR (edit), others read | Built-in and custom KPIs, formula preview |
| `/plans` | Reduction plans | HR, Legal, Finance, Approver, Viewer | Plan list |
| `/plans/new` | New plan | HR | Describe, scope, method, targets, weights |
| `/plans/[id]` | Plan | By role | Overview, ranking, fairness, compliance, approvals, cases, audit, AI drafts |
| `/notices` | Notices | HR, Legal, Approver | Batches, drafts, templates, sent messages |
| `/notices/batches/[id]` | Notice batch | HR, Legal, Approver | Per-message preview, exclusions, test send, approval, release, delivery and acknowledgement |
| `/notices/templates/[id]` | Template | Legal, HR | Editor, merge fields, versions, legal approval |
| `/cases` | Exit cases | HR, Manager (own team), others read | Case list and filters |
| `/cases/[id]` | Exit case | By role | Timeline, reason and evidence, dates, tasks, clearance, FNF, documents, approvals, audit |
| `/fnf`, `/fnf/[id]` | FNF | Finance, HR, Legal | Queue, statement lines with rules, approvals, payment, exports |
| `/grievances` | Grievances | HR, Legal | Open items, deadlines, outcomes, appeals |
| `/rules` | Jurisdiction rules | Legal, HR, Finance, Approver | Rulesets, rules with sources, verification, reason wording |
| `/integrations` | Integrations | Admin | Connections, sync runs, conflicts |
| `/audit` | Audit log | Legal, Admin | Timeline, filters, chain verification, export |
| `/users` | Team & access | Admin | Users, roles, MFA reset, organisation settings |
| `/account` | My account | All staff | Profile, sessions, MFA, notification settings |
| `/me/case` | My exit | Employee | Own notices, dates, documents, acknowledgement, grievances and appeal |
| `/me/activate` | Activate | Employee (invite link) | Set a password for self-service |
| `/ack/[token]` | Acknowledge | Public (token) | Confirm receipt of a notice |

**Employee self-service** is a separate, limited view. HR invites the employee from their case; the employee sets a password and sees only their own case and documents. They can't see scores, other people, or plan details.

**Everywhere:** command palette (⌘K), light and dark theme, keyboard navigation, toast confirmations. Charts use a colour-blind-checked palette; warnings and statuses always carry an icon and a label, not colour alone.

---

## Architecture

```
Browser ──▶ Next.js (web :3100) ──/api/*──▶ FastAPI (api :8000) ──▶ SQLite / PostgreSQL
                                                 ▲                       ▲
                                                 │ queue_jobs table      │
                                            Worker (python -m app.worker)┘
                                              ├─ mail: capture (viewer :8025) / SMTP / SES
                                              ├─ WeasyPrint (PDF letters, reports)
                                              ├─ integrations (CSV drop, webhooks)
                                              └─ schedules: escalation, retention, weekly report

                                   Anthropic API (drafts only, from app/ai)
```

- **API and worker are separate processes** sharing the database. The worker sends notices, retries, renders and attaches PDFs, runs integration jobs, escalations, retention and the weekly report.
- **Sending is never triggered directly from a web request.** The API queues jobs; the worker performs them, so retries and throttling don't block anyone.
- **Mail in development** is captured in the database and shown by the built-in mail viewer on port 8025. Any address at `@bounce.invalid` simulates a bounce. Live sending requires `MAIL_PROVIDER` and `APP_ENV` of `staging` or `production`.
- **Time is always UTC in storage**, shown in the organisation's timezone (default Asia/Kolkata).
- **Money is always integer paise** in storage and calculation.

### Stack

| Layer | Technology |
|---|---|
| Web | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui on Base UI, lucide icons, sonner toasts |
| API | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Worker | Same codebase, `python -m app.worker`, queue in the database |
| Database | SQLite (development), PostgreSQL via `DATABASE_URL` |
| Documents | Jinja2 templates to PDF via WeasyPrint; PDF encryption via pypdf |
| Security | scrypt, pyotp (TOTP), cryptography (AES-256-GCM) |
| AI | Anthropic Python SDK, only in `app/ai` |
| Tests | pytest, Vitest, Playwright |

### Repository layout

```
workforce-planner/
├── setup.sh / dev.sh / test.sh
├── rules/
│   ├── india/2026.1.yaml           Jurisdiction ruleset (placeholder, unverified)
│   └── README.md                   How rulesets are written and verified
├── templates/
│   ├── notices/                    Notice templates (front matter + body)
│   └── documents/                  Letter, FNF statement and certificate templates (HTML)
├── seed/
│   ├── generate.py                 Deterministic synthetic data
│   └── employees.csv, payroll.csv, reviews.csv
├── brand/                          Logo sources and processing script
├── apps/api/
│   ├── app/
│   │   ├── main.py                 App, request-ID middleware, routers
│   │   ├── config.py, db.py, models.py, schemas.py, serialize.py
│   │   ├── auth.py, deps.py        Sessions, MFA, rate limiting, role guards
│   │   ├── crypto.py, storage.py   Encryption, hashing, encrypted file store
│   │   ├── importer.py, retention.py, mail.py, mailview.py, notify.py
│   │   ├── queue.py, worker.py     Database queue, handlers, schedules
│   │   ├── people/                 Visibility, masking, history
│   │   ├── performance/            Calibration, PIP rules, evidence, missing-evidence
│   │   ├── kpi/                    Built-in factors, custom KPIs
│   │   ├── scoring/                Scoring engine, hard exclusions
│   │   ├── fairness/               Four-fifths analysis
│   │   ├── plans/                  Plan methods, fairness gate, compliance checks
│   │   ├── reasons/                Reason codes, evidence checks, protected terms
│   │   ├── notices/                Templates, drafting, batches, sending
│   │   ├── exits/                  States, tasks, notice periods, case service
│   │   ├── compliance/             Expression language, ruleset loader
│   │   ├── fnf/                    Components, calculator, statements
│   │   ├── documents/              PDF generation, sealing, encryption
│   │   ├── clearance/              Checklists and ticket hooks
│   │   ├── grievances/             Intake, review, appeal
│   │   ├── workflow/               Approval engine, sequences, escalation
│   │   ├── audit/                  Hash-chained writer and verifier
│   │   ├── integrations/           Providers, HRIS CSV, webhooks
│   │   ├── reports/                Defensibility pack, exit file, exports, weekly report
│   │   ├── ai/                     Drafting only
│   │   └── routers/
│   ├── migrations/
│   └── tests/
└── apps/web/
    ├── app/(public)/               Landing, login, activation, acknowledgement
    ├── app/(app)/                  Staff pages
    ├── app/(self)/me/              Employee self-service
    ├── components/
    ├── lib/
    └── tests/                      Vitest (unit) and Playwright (e2e)
```

---

## Data model

| Table | Purpose |
|---|---|
| `orgs` | Organisations and settings (timezone, test addresses, retention, escalation days) |
| `users` | Staff accounts, role, MFA secret (encrypted), active flag, linked employee code |
| `employee_accounts` | Employee self-service logins, linked to an employee record |
| `auth_sessions`, `login_attempts` | Hashed session tokens; rate-limit records |
| `employees`, `employee_history` | People and their changes over time |
| `goals`, `goal_progress` | Performance goals and progress entries |
| `checkins`, `checkin_actions` | One-to-ones and action items |
| `review_cycles`, `reviews` | Cycles and per-person ratings |
| `feedback` | Structured feedback |
| `pips`, `pip_milestones` | Improvement plans and milestone outcomes |
| `evidence` | Attachment metadata (encrypted blob reference, hash, scan status) |
| `custom_kpis` | Formula KPIs |
| `plans`, `plan_results`, `plan_overrides` | Reduction plans with method snapshot, per-person results, overrides |
| `approvals` | Generic approval steps and decisions, bound to a content hash |
| `rulesets`, `rules` | Versioned jurisdiction rules with sources and verification |
| `notice_templates`, `notice_drafts` | Templates and per-employee drafts, versioned with content hash |
| `notice_batches`, `notice_messages` | Batches and per-message send and delivery status |
| `acknowledgements` | Receipt confirmations (time, IP) |
| `exit_cases`, `exit_tasks` | Cases with state and dates; tasks with owners and due dates |
| `payroll_inputs` | Payroll data for FNF, per employee per period |
| `fnf_statements`, `fnf_lines` | Versioned FNF with per-line rule reference |
| `documents` | Issued documents, version, hash |
| `clearance_items` | Access, asset, handover and sign-off items |
| `grievances`, `appeals` | Grievances and decisions |
| `integrations`, `integration_runs` | Configuration (secrets encrypted) and sync history |
| `ai_drafts` | AI-written text (labelled) |
| `notifications` | In-app notifications |
| `queue_jobs` | Worker queue |
| `captured_mail` | Development mail capture |
| `audit_log` | Hash-chained, append-only |

Every table except `orgs` has `org_id`. Schema changes go through Alembic.

---

## API reference

All endpoints are under `/api`. Except `health`, `auth/login`, `auth/activate` and `acknowledge/{token}`, endpoints require a session; staff roles that need MFA get 401 until it's complete. Interactive docs are at http://localhost:8000/docs.

**Auth, account and administration**

| Method | Path | Who | Description |
|---|---|---|---|
| GET | `/health` | public | Liveness |
| POST | `/auth/login`, `/auth/mfa/verify`, `/auth/logout` | public / signed in | Sign-in flow |
| GET/PATCH | `/auth/me` | signed in | Current user, notification preference |
| GET/DELETE | `/auth/sessions`, `/auth/sessions/{id}` | signed in | Own sessions |
| POST | `/auth/activate` | public (invite token) | Employee self-service activation |
| GET/POST/PATCH | `/users`, `/users/{id}` | admin | Staff accounts, roles, MFA reset |
| GET/PATCH | `/org` | admin (read: staff) | Organisation settings |
| GET | `/dashboard`, `/notifications` | staff | Home and notifications |

**People and performance**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/POST | `/employees` | by role / hr | List with filters; create |
| GET | `/employees/meta`, `/employees/by-code/{code}` | by role | Filter values; full profile |
| GET/PATCH | `/employees/{id}` | by role / hr | Read; edit |
| POST | `/employees/import`, `/employees/payroll/import` | hr; hr, finance | CSV imports |
| GET/PUT | `/employees/{id}/payroll` | hr, finance | Payroll inputs |
| GET | `/employees/{id}/export` | legal | Data subject export |
| POST | `/employees/{id}/pseudonymise` | admin | Pseudonymise (blocked by legal hold) |
| GET | `/performance/overview`, `/performance/missing-evidence` | hr, legal, manager | Pipeline and reports |
| POST/GET/PUT | `/performance/cycles`, `/cycles/{id}`, `/cycles/{id}/reviews`, `/cycles/{id}/close` | hr | Cycles and reviews |
| POST | `/performance/reviews/{id}/calibrate` | hr | Calibrate a rating |
| POST | `/performance/goals`, `/goals/{id}/progress`, `/checkins`, `/feedback` | manager, hr | Goals, check-ins, feedback |
| GET/POST | `/performance/pips`, `/pips/{id}/activate`, `/milestones`, `/ack`, `/close` | hr, legal, manager (propose) | PIPs |
| POST | `/performance/evidence` | hr, manager | Upload evidence |

**Plans, KPIs and approvals**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/POST | `/kpis`, `/kpis/fields`, `/kpis/preview`, `/kpis/{id}/archive` | by role / hr | KPI library |
| GET/POST | `/plans` | by role / hr | List, create |
| GET/PATCH | `/plans/{id}` | by role / hr | Details, edit draft |
| POST | `/plans/{id}/run` | hr | Score and rank |
| GET | `/plans/{id}/results`, `/fairness`, `/compliance`, `/approvals` | by role | Results and checks |
| POST | `/plans/{id}/overrides`, `/overrides/{oid}/revoke` | hr | Overrides |
| POST | `/plans/{id}/submit`, `/decision`, `/new-version` | hr / step role | Approval flow |
| GET | `/plans/{id}/export.csv`, `/plans/{id}/report.pdf?external=` | by role | Exports |
| GET | `/approvals/pending`, `/approvals/{type}/{id}` | staff | Approval queue and history |

**Rules and reasons**

| Method | Path | Who | Description |
|---|---|---|---|
| GET | `/rulesets`, `/rulesets/{id}` | legal, hr, finance, approver | Rulesets and rules |
| POST | `/rulesets/{id}/verify`, `/rulesets/reload` | legal | Record verification; reload YAML |
| GET/POST | `/reasons`, `/reasons/{code}/approve-wording` | by role / legal | Reason codes and wording |

**Notices**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/PATCH | `/notice-templates`, `/notice-templates/{id}` | legal, hr | Templates and versions |
| POST | `/notice-templates/{id}/approve` | legal | Legal approval |
| POST | `/plans/{id}/notice-drafts` | hr | Draft notices for a plan's cases |
| GET/PATCH | `/notice-drafts`, `/notice-drafts/{id}` | hr, legal | Drafts (edits are versioned) |
| GET/POST | `/notice-batches`, `/notice-batches/{id}` | hr | Batches |
| POST | `/notice-batches/{id}/exclude`, `/submit`, `/test-send` | hr | Prepare |
| POST | `/notice-batches/{id}/approve` | legal, approver | Approve exact content hashes |
| POST | `/notice-batches/{id}/release` | hr, admin | Queue for throttled sending |
| GET | `/notice-messages`, `/notice-batches/{id}/messages/{mid}` | hr, legal | Delivery status, preview |
| GET/POST | `/acknowledge/{token}` | public (token) | Employee acknowledgement |

**Exit cases, FNF, documents, clearance**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/POST | `/exit-cases` | by role / hr | List; create from an approved plan |
| GET | `/exit-cases/{id}` | by role | Full case detail |
| POST | `/exit-cases/{id}/reason`, `/reason/decision`, `/evidence` | hr / legal | Reason and evidence |
| POST | `/exit-cases/{id}/dates`, `/last-day` | hr | Notice dates; actual last day |
| POST | `/exit-cases/{id}/hold`, `/release-hold`, `/withdraw` | legal, hr | Holds and withdrawal |
| PATCH | `/exit-cases/{id}/tasks/{tid}`, `/clearance/{iid}` | owner role | Tasks and clearance |
| POST | `/exit-cases/{id}/clearance/exception`, `/exception/decision` | hr / approver | Clearance exception |
| POST/GET | `/exit-cases/{id}/fnf`, `/fnf/what-if` | hr, finance | Compute FNF draft; comparison |
| POST/GET | `/exit-cases/{id}/documents`, `/documents/{did}/download` | hr | Issue and download documents |
| POST | `/exit-cases/{id}/mark-effective`, `/mark-effective/decision` | hr / approver | Mark effective |
| POST | `/exit-cases/{id}/push-hris`, `/push-hris/decision` | hr / finance | Write exit to HRIS |
| POST | `/exit-cases/{id}/close`, `/invite` | hr | Close; invite to self-service |
| GET | `/exit-cases/{id}/file.pdf` | by role | Exit file |
| GET | `/fnf`, `/fnf/{id}` | finance, hr, legal | FNF queue and statement |
| POST | `/fnf/{id}/submit`, `/decision`, `/mark-paid` | hr, finance / finance, legal | FNF approval and payment |
| GET | `/fnf/export/payroll.csv` | finance | CSV for payroll |

**Grievances and self-service**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/POST | `/grievances`, `/grievances/{id}` | hr, legal | Log and view |
| POST | `/grievances/{id}/acknowledge`, `/decision`, `/appeal/decision` | hr, legal | Review and outcomes |
| GET | `/me/case` | employee | Own case, notices, documents, grievances |
| POST | `/me/acknowledge/{mid}`, `/me/grievances`, `/me/grievances/{id}/appeal` | employee | Acknowledge, log, appeal (once) |
| GET | `/me/documents/{id}/download` | employee | Own documents |

**Integrations, audit, AI**

| Method | Path | Who | Description |
|---|---|---|---|
| GET/PUT | `/integrations` | admin | Configure integrations |
| POST | `/integrations/hris/sync`, `/integrations/runs/{id}/apply` | admin | HRIS pull and conflict review |
| GET | `/audit`, `/audit/verify`, `/audit/export.json` | legal, admin | Entries, chain verification, export |
| GET | `/reports/hris.csv` | finance, hr | HRIS exits CSV |
| POST/GET | `/plans/{id}/ai/summary`, `/ai/explain`, `/ai/drafts` | hr, approver, legal | AI plan drafts |
| POST/GET | `/exit-cases/{id}/ai/notice-draft`, `/ai/reply`, `/ai/drafts`, `/ai/drafts/{aid}/use` | hr, legal | AI case drafts |
| POST | `/grievances/{id}/ai/summary` | hr, legal | AI grievance summary |

Errors: 401 not signed in or MFA incomplete, 403 wrong role or separation-of-duties violation, 404 not found (including other organisations), 409 wrong state or content changed since approval, 422 invalid input, 423 locked (case on hold, legal hold, or plan with unverified rules in production mode), 429 too many sign-in attempts, 503 AI not configured.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `development`, `staging`, `production`. Live mail and production checks require `staging` or `production`; `/api/dev/totp` exists only in development. |
| `DATABASE_URL` | `sqlite:///data/app.db` (in `apps/api`) | Database |
| `SECRET_KEY` | generated into `apps/api/data/.dev_secret_key` in development | Encryption root; required outside development |
| `FILES_DIR`, `EXPORTS_DIR` | `apps/api/data/files`, `apps/api/data/exports` | Encrypted file store; CSV drop and exports |
| `MAIL_PROVIDER` | `capture` | `capture`, `smtp`, `ses` (SES through its SMTP interface) |
| `MAIL_FROM` | `Unlink <no-reply@unlink.local>` | Sender address (must be verified with the provider) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` (or `SES_SMTP_*`) | unset | Provider credentials |
| `MAIL_RATE_PER_MINUTE` | `20` | Throttle for batch release |
| `ANTHROPIC_API_KEY` | unset | Enables AI drafting |
| `RULESET_MODE` | `development` | `production` blocks plan approval while unverified rules are in use |
| `DEFAULT_TIMEZONE` | `Asia/Kolkata` | Display timezone |
| `WEB_BASE_URL` | `http://localhost:3100` | Links in emails (acknowledgement, activation, notifications) |
| `CLAMD_SOCKET` | unset | ClamAV daemon socket for upload scanning |
| `MAX_UPLOAD_BYTES` | `10485760` | Upload size limit |
| `KMS_KEY_ID`, `REDIS_URL` | unset | Reserved; not used yet (see [Implementation status](#implementation-status)) |
| `DYLD_FALLBACK_LIBRARY_PATH` | set by scripts (macOS) | Finds pango for PDFs |
| `API_URL` | `http://127.0.0.1:8000` | Web app proxy target |

---

## Testing

```bash
./test.sh                                         # everything
cd apps/api && uv run pytest                      # API, worker, rules, FNF, audit, privacy
cd apps/api && uv run pytest tests/test_fnf_calc.py   # FNF worked examples only
cd apps/web && npm test                           # unit tests
cd apps/web && npx playwright test                # end-to-end (isolated DB on :8001, build on :3101)
```

**What the tests cover**

- **Scoring and fairness:** known-value maths, ties, exclusions, impact ratios, intersectional groups.
- **Exclusions and protection:** protected people can't be selected, overridden in, or exited under any role, including admin.
- **Reason codes:** evidence required, protected-term blocking, "Other" needs Legal approval.
- **Notices:** template gating, merge-field validation, content-hash approval, edits after approval are blocked, test send, throttled release, retries, bounce handling, acknowledgement, consultation sequencing.
- **FNF:** a full worked example (net ₹4,94,051.00, payment due 2026-11-24), integer-paise rounding, notice shortfall, what-if, locked statements, separation of duties.
- **Notice periods:** last-working-day calculation per rule and employment type.
- **Approvals:** separation of duties, step ordering, rejection returns to draft, escalation.
- **Workflow:** exit-case transitions, holds, withdrawal, effective and HRIS gates, clearance-gated relieving letter.
- **Audit:** hash chain intact, tampering detected, append-only at ORM and database level.
- **Privacy:** no PII in logs or AI prompts, masking by role, self-service sees only own data, data export and pseudonymisation.
- **Security:** org isolation, login rate limiting, MFA enforcement, upload checks, encrypted attachments.
- **Compliance guard:** production mode blocks plan approval with unverified rules.
- **End-to-end (Playwright):** sign-in with MFA, a plan approved by Legal, Finance and Approver followed by exit cases, role-shaped navigation, rule verification banner and audit-chain check, custom KPIs, and the command palette.
- **Worker:** `python -m app.worker --check` must register every job handler (a test runs it as a separate process).

Test data uses synthetic people only. FNF and notice-period tests use worked examples that counsel must check against the ruleset.

---

## Development guide

**Migrations:** `cd apps/api && uv run alembic revision --autogenerate -m "..." && uv run alembic upgrade head`

**Reset demo data:** `rm apps/api/data/app.db && cd apps/api && uv run alembic upgrade head && uv run python -m app.cli seed`. Regenerate the CSVs with `python3 seed/generate.py`.

**Adding a selection factor:** add it to `app/kpi/library.py`.

**Adding a jurisdiction rule:** add it to `rules/<jurisdiction>/` with source and effective date, leave `verified_by` empty, add a worked-example test, and run `uv run python -m app.cli load-rules` (or Reload on `/rules`). Legal verifies it through `/rules`.

**Adding a notice template:** add a file to `templates/notices/` with front matter. It loads as `draft`; Legal approves it on `/notices`.

**Adding a reason code:** add it to `CODES` in `app/reasons/__init__.py` with its evidence check. Legal must approve the wording.

**Worker:** `uv run python -m app.worker` (started by `./dev.sh`). Register a job type with `@handler("name")` and queue it with `queue.enqueue(...)`.

**Where the rules live**

- Hard exclusions: `app/scoring/exclusions.py`
- Approval sequences: `app/workflow/sequences.py`
- Exit case state machine: `app/exits/states.py`
- Stage tasks and clearance checklist: `app/exits/tasks.py`
- FNF components: `app/fnf/components.py`
- Protected-term list: `app/reasons/protected_terms.yaml` (reviewed by Legal)
- Mail providers: `app/mail.py`
- AI prompts and model: `app/ai/drafting.py`

---

## Implementation status

Everything in this README is implemented and tested unless listed here.

| Area | Status |
|---|---|
| Vendor integrations (Keka, Darwinbox, greytHR, Jira, ServiceNow, Freshdesk, SendGrid, e-signature) | **Planned.** The provider list shows them as "planned". HRIS and payroll work through CSV; ticketing through a generic webhook. |
| SSO (SAML, OIDC) | Planned. |
| KMS | Not used. Field and file encryption use an AES-256-GCM key derived from `SECRET_KEY`. |
| Redis queue | Not used. The worker queue is the `queue_jobs` table, which is fine for a single worker. |
| Virus scanning | Hook only: scanning runs when `CLAMD_SOCKET` points at a ClamAV daemon; otherwise files are marked "not scanned". |
| FNF approver step | The sequence is Finance → Legal (when needed). A separate final "Approver" confirmation can be added in `workflow/sequences.py`. |
| Field-level processing purposes | Documented, not stored per field. |
| Legal content | All rules, templates, reason wording and protected terms are unverified placeholders. |

## Decisions taken

The original plan listed four questions to settle before building. These defaults were used and can be changed:

1. **Live email:** capture-only until Legal signs off. Live sending works only with `APP_ENV=staging` or `production` and a configured `MAIL_PROVIDER`.
2. **HRIS and payroll:** CSV first (people import, payroll import, HRIS drop folder and FNF export). The first real integration will set the payroll input format.
3. **Employee self-service:** included in v1 (acknowledgements, documents, grievances and appeals).
4. **Approvers:** the default sequences in `app/workflow/sequences.py` (see [Approvals](#approvals)). Map your organisation's approvers to the Legal, Finance and Approver roles, or edit the sequences.

## Limitations

- **Legal content is unverified.** The India ruleset, templates, and reason wording are placeholders until a qualified lawyer approves them.
- **Payroll is not run here.** FNF amounts depend on the inputs you provide. Unlink calculates from those inputs and doesn't move money.
- **Statutory filings** (tax, provident fund, state labour returns, notice-to-government filings) are not generated. Unlink tracks deadlines and exports data.
- **Only India is configured.** Other jurisdictions need their own rulesets and templates.
- **Mail deliverability** depends on your sender domain setup (SPF, DKIM, DMARC).
- **Notification-to-employee requirements** vary by law and contract. The system enforces the sequence you configure; it doesn't decide what the law requires.
- **Single organisation per user.**
- **The fairness check is a screening heuristic**, not a legal test.
- **AI drafts need review** and can be wrong. They are never sent automatically.
