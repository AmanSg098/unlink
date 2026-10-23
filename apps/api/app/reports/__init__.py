"""Defensibility pack (per plan), exit file (per case), and exports."""

import csv
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import rulebook
from app.deps import Ctx
from app.documents import html_to_pdf
from app.grievances import ref as grievance_ref
from app.models import (
    Acknowledgement,
    Appeal,
    AuditLog,
    ClearanceItem,
    Document,
    Employee,
    ExitCase,
    FnfLine,
    FnfStatement,
    Grievance,
    NoticeBatch,
    NoticeDraft,
    NoticeMessage,
    NoticeTemplate,
    Org,
    Plan,
    PlanOverride,
    utcnow,
)
from app.notices import reason_hash
from app.plans.service import compliance_checks, fairness, results_rows
from app.reasons import CODES, evidence_status
from app.workflow import approvals

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"]))
_env.globals["money"] = lambda p: f"₹{p / 100:,.2f}"


def _rupees(p: int | None) -> str:
    return "-" if p is None else f"₹{p / 100:,.0f}"


def defensibility_context(db: Session, ctx: Ctx, p: Plan, external: bool = False) -> dict:
    book = rulebook(db, ctx.org_id, p.ruleset_id)
    rows = results_rows(db, ctx, p)
    cases = {c.employee_id: c for c in db.scalars(select(ExitCase).where(ExitCase.plan_id == p.id))}
    total_w = sum(w for w in (p.weights or {}).values() if w > 0) or 1
    snap = p.kpi_snapshot or {}
    factors = [{**snap.get(k, {"label": k, "description": "", "higher_is_better": True}), "weight": w / total_w}
               for k, w in (p.weights or {}).items() if w > 0]
    selected = []
    for r, e in sorted(rows, key=lambda t: (t[0].rank is None, t[0].rank or 0)):
        if not r.final_selected:
            continue
        c = cases.get(e.id)
        selected.append({"reason": f"{c.reason_code} · {CODES[c.reason_code].name}" if c and c.reason_code else "Not yet assigned",
                         "name": e.full_name, "code": e.employee_code, "department": e.department, "role": e.role,
                         "score": f"{r.score:.1f}" if r.score is not None else "-",
                         "basis": c.selection_basis if c else ("override" if not r.algo_selected else "algorithm"),
                         "state": c.state if c else "no case"})
    selected.sort(key=lambda s: s["reason"])
    exclusions = Counter(r.exclusion_reason for r, _ in rows if r.excluded)
    codes = {e.id: e.employee_code for _, e in rows}
    overrides = [{"code": codes.get(o.employee_id, o.employee_id), "action": o.action, "by": o.created_by,
                  "at": o.created_at.strftime("%Y-%m-%d"), "justification": o.justification,
                  "status": "revoked" if o.revoked else "active"}
                 for o in db.scalars(select(PlanOverride).where(PlanOverride.plan_id == p.id).order_by(PlanOverride.id))]
    case_ids = [c.id for c in cases.values()]
    batches, templates_used = [], set()
    if case_ids:
        msgs = db.scalars(select(NoticeMessage).where(NoticeMessage.exit_case_id.in_(case_ids),
                                                      NoticeMessage.is_test.is_(False))).all()
        acks = set(db.scalars(select(Acknowledgement.message_id).where(Acknowledgement.message_id.in_([m.id for m in msgs] or [0]))))
        by_batch = defaultdict(list)
        for m in msgs:
            by_batch[m.batch_id].append(m)
            d = db.get(NoticeDraft, m.draft_id)
            t = db.get(NoticeTemplate, d.template_id)
            templates_used.add(f"{t.title} v{t.version}")
        for bid, ms in by_batch.items():
            b = db.get(NoticeBatch, bid)
            appr = [a.decided_by for a in approvals.history(db, ctx.org_id, "notice_batch", bid) if a.status == "approved"]
            batches.append({"name": b.name, "status": b.status, "approved_by": ", ".join(appr) or "-",
                            "released_at": b.released_at.strftime("%Y-%m-%d %H:%M") if b.released_at else None,
                            "messages": sum(1 for m in ms if not m.excluded),
                            "delivered": sum(1 for m in ms if m.status in ("sent", "delivered")),
                            "bounced": sum(1 for m in ms if m.status == "bounced"),
                            "acknowledged": sum(1 for m in ms if m.id in acks)})
    fnf_totals: dict[tuple[str, str], int] = defaultdict(int)
    for st in db.scalars(select(FnfStatement).where(FnfStatement.exit_case_id.in_(case_ids or [0]),
                                                    FnfStatement.status.in_(("approved", "paid")))):
        for ln in db.scalars(select(FnfLine).where(FnfLine.statement_id == st.id)):
            fnf_totals[(ln.label, ln.kind)] += ln.amount_paise
    audit_rows = audit.for_entity(db, ctx, "plan", p.id, related=("override", "exit_case", "notice_batch"), limit=60)
    f = fairness(db, ctx, p)
    scope = ", ".join([*p.filters.get("departments", []), *p.filters.get("locations", []), *p.filters.get("roles", [])]) \
        or "whole organisation"
    targets = ", ".join(x for x in [f"{p.target_count} roles" if p.target_count else "",
                                     f"{_rupees(p.target_cost_paise)} saving" if p.target_cost_paise else ""] if x) or "-"
    rs = book.ruleset
    ruleset_label = (f"{rs.title} v{rs.version} ({len(book.rules) - len(book.unverified)}/{len(book.rules)} rules verified)"
                     if rs else "none")
    return {
        "plan": p, "org_name": db.get(Org, ctx.org_id).name, "external": external,
        "approvals": approvals.history(db, ctx.org_id, "plan", p.id), "checks": compliance_checks(db, ctx, p),
        "factors": factors, "fairness": f, "selected": selected, "exclusions": dict(exclusions),
        "overrides": overrides, "batches": batches, "templates_used": sorted(templates_used),
        "fnf_totals": [{"label": k[0], "kind": k[1], "total": v} for k, v in sorted(fnf_totals.items())],
        "audit": list(reversed(audit_rows)), "scope": scope, "targets": targets, "ruleset_label": ruleset_label,
        "generated_at": utcnow().strftime("%Y-%m-%d %H:%M UTC"), "generated_by": ctx.user,
    }


def defensibility_pdf(db: Session, ctx: Ctx, p: Plan, external: bool = False) -> bytes:
    return html_to_pdf(_env.get_template("defensibility_pack.html").render(**defensibility_context(db, ctx, p, external)))


def exit_file_context(db: Session, ctx: Ctx, case: ExitCase) -> dict:
    e = db.get(Employee, case.employee_id)
    plan = db.get(Plan, case.plan_id)
    book = rulebook(db, ctx.org_id, plan.ruleset_id)
    approved_other = approvals.is_approved(db, ctx.org_id, "reason_other", case.id, reason_hash(case))
    msgs = db.scalars(select(NoticeMessage).where(NoticeMessage.exit_case_id == case.id, NoticeMessage.is_test.is_(False))
                      .order_by(NoticeMessage.id)).all()
    acks = {a.message_id: a.acknowledged_at for a in db.scalars(select(Acknowledgement).where(
        Acknowledgement.message_id.in_([m.id for m in msgs] or [0])))}
    fnf = db.scalar(select(FnfStatement).where(FnfStatement.exit_case_id == case.id)
                    .order_by(FnfStatement.version.desc()))
    grievances = []
    for g in db.scalars(select(Grievance).where(Grievance.exit_case_id == case.id)):
        a = db.scalar(select(Appeal).where(Appeal.grievance_id == g.id))
        grievances.append({"ref": grievance_ref(g), "category": g.category, "status": g.status, "outcome": g.outcome,
                           "appeal": f"{a.status}{' · ' + a.outcome if a.outcome else ''}" if a else None})
    return {
        "org_name": db.get(Org, ctx.org_id).name, "e": e, "case": case, "plan": plan,
        "reason_name": CODES[case.reason_code].name if case.reason_code in CODES else None,
        "evidence": evidence_status(db, case, e, plan, book, approved_other),
        "trace": (case.lwd_trace or {}).get("steps", []),
        "messages": [{"subject": m.subject, "status": m.status, "sent_at": m.sent_at, "content_hash": m.content_hash,
                      "ack": acks.get(m.id)} for m in msgs],
        "fnf": fnf, "fnf_lines": db.scalars(select(FnfLine).where(FnfLine.statement_id == fnf.id)
                                            .order_by(FnfLine.position)).all() if fnf else [],
        "documents": db.scalars(select(Document).where(Document.exit_case_id == case.id).order_by(Document.id)).all(),
        "clearance": db.scalars(select(ClearanceItem).where(ClearanceItem.exit_case_id == case.id)
                                .order_by(ClearanceItem.id)).all(),
        "grievances": grievances,
        "audit": list(reversed(audit.for_entity(db, ctx, "exit_case", case.id,
                                                related=("notice_message", "notice_draft", "fnf", "document",
                                                         "clearance", "grievance", "evidence")))),
        "generated_at": utcnow().strftime("%Y-%m-%d %H:%M UTC"), "generated_by": ctx.user,
    }


def exit_file_pdf(db: Session, ctx: Ctx, case: ExitCase) -> bytes:
    return html_to_pdf(_env.get_template("exit_file.html").render(**exit_file_context(db, ctx, case)))


def plan_csv(db: Session, ctx: Ctx, p: Plan) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"# Plan only. Plan '{p.name}' v{p.version} status={p.status}"])
    w.writerow(["employee_code", "full_name", "department", "role", "location", "score", "rank", "basis"])
    for r, e in sorted(results_rows(db, ctx, p), key=lambda t: (t[0].rank is None, t[0].rank or 0)):
        if r.final_selected:
            w.writerow([e.employee_code, e.full_name, e.department, e.role, e.location,
                        r.score, r.rank, "algorithm" if r.algo_selected else "manual override"])
    return buf.getvalue()


def hris_csv(db: Session, ctx: Ctx) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["employee_code", "state", "notice_date", "last_working_day", "effective_at", "reason_code"])
    for c in db.scalars(select(ExitCase).where(ExitCase.org_id == ctx.org_id).order_by(ExitCase.id)):
        e = db.get(Employee, c.employee_id)
        w.writerow([e.employee_code, c.state, c.notice_date or "", c.actual_last_day or c.last_working_day or "",
                    c.effective_at.isoformat() if c.effective_at else "", c.reason_code or ""])
    return buf.getvalue()


def audit_json(db: Session, ctx: Ctx) -> str:
    rows = db.scalars(select(AuditLog).where(AuditLog.org_id == ctx.org_id).order_by(AuditLog.id))
    return json.dumps({"org_id": ctx.org_id, "exported_at": utcnow().isoformat(), "verification": audit.verify_chain(db, ctx.org_id),
                       "entries": [{"id": a.id, "created_at": a.created_at.isoformat(), "actor": a.actor,
                                    "entity_type": a.entity_type, "entity_id": a.entity_id, "action": a.action,
                                    "before": a.before, "after": a.after, "justification": a.justification,
                                    "request_id": a.request_id, "prev_hash": a.prev_hash, "hash": a.hash}
                                   for a in rows]}, default=str, indent=1)
