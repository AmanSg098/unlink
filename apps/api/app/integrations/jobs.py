"""Worker jobs for integrations: ticket creation, messaging notifications, HRIS sync and write-back."""

import csv
import io
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.importer import parse_people_csv
from app.integrations import enabled_integration, get_secrets, post_json
from app.models import ClearanceItem, Employee, ExitCase, IntegrationRun, QueueJob, utcnow
from app.worker import handler


@handler("ticket_create")
def ticket_create(db: Session, job: QueueJob) -> None:
    it = db.get(ClearanceItem, job.payload["clearance_item_id"])
    integ = enabled_integration(db, job.org_id, "ticketing")
    if it is None or integ is None or integ.provider != "webhook":
        return
    case = db.get(ExitCase, it.exit_case_id)
    e = db.get(Employee, case.employee_id)
    payload = {"type": "access_revocation", "item": it.key, "label": it.label, "employee_code": e.employee_code,
               "due_date": (case.actual_last_day or case.last_working_day or date.today()).isoformat(),
               "exit_case_id": case.id}
    status = post_json(integ.config["url"], payload, get_secrets(integ).get("token"))
    it.ticket_ref = f"webhook:{status}"
    audit.record_raw(db, job.org_id, "system:integrations", "clearance", it.id, "ticket_created", None,
                     {"provider": "webhook", "status": status, "exit_case_id": case.id})


@handler("messaging_notify")
def messaging_notify(db: Session, job: QueueJob) -> None:
    integ = enabled_integration(db, job.org_id, "messaging")
    if integ is None:
        return
    url = get_secrets(integ).get("url")
    if url:
        post_json(url, {"text": job.payload["text"]})


@handler("hris_sync")
def hris_sync(db: Session, job: QueueJob) -> None:
    """Read people.csv from the inbox; record differences as conflicts for review (nothing is overwritten)."""
    integ = enabled_integration(db, job.org_id, "hris")
    run = db.get(IntegrationRun, job.payload["run_id"])
    path = Path(integ.config.get("inbox_path", "")) / "people.csv"
    if not path.exists():
        run.status, run.error, run.finished_at = "failed", f"{path} not found", utcnow()
        return
    rows, errors = parse_people_csv(path.read_text())
    current = {e.employee_code: e for e in db.scalars(select(Employee).where(Employee.org_id == job.org_id))}
    conflicts, new = [], []
    for code, fields in rows.items():
        e = current.get(code)
        if e is None:
            new.append(code)
            continue
        for k, v in fields.items():
            if k in ("employee_code",):
                continue
            cur = getattr(e, k)
            if (cur.isoformat() if hasattr(cur, "isoformat") else cur) != (v.isoformat() if hasattr(v, "isoformat") else v):
                conflicts.append({"employee_code": code, "field": k,
                                  "current": cur.isoformat() if hasattr(cur, "isoformat") else cur,
                                  "incoming": v.isoformat() if hasattr(v, "isoformat") else v})
    run.summary = {"rows": len(rows), "new": new, "conflicts": conflicts, "errors": errors}
    run.status = "needs_review" if conflicts or new else "succeeded"
    run.finished_at = utcnow()


@handler("hris_push")
def hris_push(db: Session, job: QueueJob) -> None:
    case = db.get(ExitCase, job.payload["exit_case_id"])
    integ = enabled_integration(db, job.org_id, "hris")
    e = db.get(Employee, case.employee_id)
    if integ is None or integ.provider != "csv_drop":
        raise RuntimeError("No HRIS integration that supports write-back is enabled")
    out = Path(integ.config.get("outbox_path", ""))
    out.mkdir(parents=True, exist_ok=True)
    f = out / "exits.csv"
    new_file = not f.exists()
    buf = io.StringIO()
    w = csv.writer(buf)
    if new_file:
        w.writerow(["employee_code", "status", "last_working_day", "effective_at", "reason_code", "exit_case_id"])
    w.writerow([e.employee_code, "exited", (case.actual_last_day or case.last_working_day),
                case.effective_at.isoformat() if case.effective_at else "", case.reason_code or "", case.id])
    with f.open("a") as fh:
        fh.write(buf.getvalue())
    case.hris_pushed_at = utcnow()
    audit.record_raw(db, job.org_id, job.payload.get("approved_by", "system:integrations"), "exit_case", case.id,
                     "hris_pushed", None, {"provider": "csv_drop", "file": str(f)})
