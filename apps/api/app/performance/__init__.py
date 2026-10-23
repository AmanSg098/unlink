"""Performance tracker: goals, check-ins, review cycles and calibration, feedback, PIPs, and evidence."""

import socket
import statistics
import struct
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, storage
from app.config import CLAMD_SOCKET, MAX_UPLOAD_BYTES
from app.crypto import sha256_bytes
from app.deps import Ctx
from app.models import Employee, Evidence, Pip, PipMilestone, Review, ReviewCycle, utcnow
from app.people import apply_changes, get_visible, visible_query

PIP_OUTCOMES = ("met", "partially_met", "not_met")
EVIDENCE_TYPES = ("review_form", "email", "incident_note", "attendance_record", "investigation_outcome",
                  "role_elimination_record", "restructuring_record", "location_decision", "signed_acceptance",
                  "decision_record", "other")
ALLOWED_UPLOADS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                   ".txt": "text/plain", ".eml": "message/rfc822",
                   ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAGIC = {".pdf": [b"%PDF"], ".png": [b"\x89PNG"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
         ".docx": [b"PK\x03\x04"]}


def employee_for(db: Session, ctx: Ctx, employee_id: int) -> Employee:
    """Managers may act only within their reporting line; HR/Legal/Admin on anyone."""
    if not ctx.has("hr", "legal", "manager"):
        raise HTTPException(403, "Not allowed")
    return get_visible(db, ctx, employee_id)


# ------------------------------------------------------------------ review cycles and calibration

def calibration(db: Session, ctx: Ctx, cycle: ReviewCycle) -> dict:
    rows = db.execute(select(Review, Employee).join(Employee, Employee.id == Review.employee_id)
                      .where(Review.cycle_id == cycle.id, Review.org_id == ctx.org_id)).all()
    by_dept: dict[str, list[float]] = {}
    for r, e in rows:
        if r.manager_rating is not None:
            by_dept.setdefault(e.department, []).append(r.manager_rating)
    stats = {}
    for d, vals in by_dept.items():
        stats[d] = {"count": len(vals), "mean": round(statistics.fmean(vals), 2),
                    "stdev": round(statistics.pstdev(vals), 2) if len(vals) > 1 else 0.0,
                    "distribution": {str(k): sum(1 for v in vals if round(v) == k) for k in range(1, cycle.scale_max + 1)}}
    outliers = []
    for r, e in rows:
        s = stats.get(e.department)
        if r.manager_rating is None or not s:
            continue
        far = s["stdev"] > 0 and abs(r.manager_rating - s["mean"]) > 1.5 * s["stdev"]
        moved = r.calibrated_rating is not None and abs(r.calibrated_rating - r.manager_rating) >= 1.5
        if far or moved:
            outliers.append({"review_id": r.id, "employee_id": e.id, "employee_code": e.employee_code,
                             "department": e.department, "manager_rating": r.manager_rating,
                             "calibrated_rating": r.calibrated_rating,
                             "why": "far from department mean" if far else "calibrated far from manager rating"})
    return {"departments": stats, "outliers": outliers}


def finalize_cycle(db: Session, ctx: Ctx, cycle: ReviewCycle) -> int:
    """Close the cycle; calibrated ratings become each employee's current performance rating."""
    if cycle.status == "closed":
        raise HTTPException(409, "Cycle is already closed")
    reviews = db.scalars(select(Review).where(Review.cycle_id == cycle.id)).all()
    missing = [r.id for r in reviews if r.calibrated_rating is None]
    if missing:
        raise HTTPException(409, f"{len(missing)} reviews have no calibrated rating yet")
    latest = db.scalar(select(ReviewCycle.period_end).where(ReviewCycle.org_id == ctx.org_id,
                                                            ReviewCycle.status == "closed")
                       .order_by(ReviewCycle.period_end.desc()).limit(1))
    n = 0
    if latest is None or cycle.period_end >= latest:  # only the newest cycle sets the current rating
        for r in reviews:
            e = db.get(Employee, r.employee_id)
            if apply_changes(db, ctx, e, {"performance_rating": r.calibrated_rating}, action="calibrated_rating"):
                n += 1
    cycle.status = "closed"
    audit.record(db, ctx, "review_cycle", cycle.id, "close", None, {"reviews": len(reviews), "ratings_updated": n})
    return n


# ------------------------------------------------------------------ PIPs

def close_pip(db: Session, ctx: Ctx, pip: Pip, outcome: str, final_review: str, final_review_on: date) -> None:
    if pip.status != "active":
        raise HTTPException(409, f"PIP is {pip.status}")
    if outcome not in PIP_OUTCOMES:
        raise HTTPException(422, f"Outcome must be one of {', '.join(PIP_OUTCOMES)}")
    if not final_review.strip():
        raise HTTPException(422, "A documented final review is required")
    milestones = db.scalars(select(PipMilestone).where(PipMilestone.pip_id == pip.id)).all()
    if outcome == "not_met":
        dated = {m.on_date for m in milestones}
        if len(dated) < 2:
            raise HTTPException(409, "A PIP can't close as 'not met' without at least two dated check-ins")
    pip.status, pip.outcome, pip.final_review, pip.final_review_on = "closed", outcome, final_review, final_review_on
    pip.closed_by, pip.closed_at = ctx.user, utcnow()
    audit.record(db, ctx, "pip", pip.id, "close", {"status": "active"},
                 {"status": "closed", "outcome": outcome, "employee_id": pip.employee_id, "milestones": len(milestones)})


def default_end(start: date) -> date:
    return start + timedelta(days=60)


# ------------------------------------------------------------------ evidence

def _clamd_scan(data: bytes) -> bool:
    """True if clean. Uses the ClamAV daemon's INSTREAM command when CLAMD_SOCKET is configured."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(30)
        s.connect(CLAMD_SOCKET)
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), 8192):
            chunk = data[i:i + 8192]
            s.sendall(struct.pack("!L", len(chunk)) + chunk)
        s.sendall(struct.pack("!L", 0))
        reply = s.recv(4096).decode(errors="replace")
    return reply.rstrip("\0").endswith("OK")


def store_evidence(db: Session, ctx: Ctx, *, employee_id: int | None, entity_type: str, entity_id: int,
                   evidence_type: str, filename: str, data: bytes) -> Evidence:
    if evidence_type not in EVIDENCE_TYPES:
        raise HTTPException(422, f"Evidence type must be one of {', '.join(EVIDENCE_TYPES)}")
    if len(data) == 0 or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413 if data else 422, f"Files must be between 1 byte and {MAX_UPLOAD_BYTES // 1_048_576} MB")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_UPLOADS:
        raise HTTPException(422, f"Allowed file types: {', '.join(sorted(ALLOWED_UPLOADS))}")
    if ext in MAGIC and not any(data.startswith(m) for m in MAGIC[ext]):
        raise HTTPException(422, "The file's contents don't match its extension")
    if ext in (".txt", ".eml"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "Text files must be UTF-8") from exc
    scan = "not_scanned"
    if CLAMD_SOCKET:
        if not _clamd_scan(data):
            raise HTTPException(422, "The file failed the virus scan")
        scan = "clean"
    ev = Evidence(org_id=ctx.org_id, employee_id=employee_id, entity_type=entity_type, entity_id=entity_id,
                  evidence_type=evidence_type, filename=filename[:255], content_type=ALLOWED_UPLOADS[ext],
                  size=len(data), sha256=sha256_bytes(data), storage_key=storage.save(ctx.org_id, data),
                  scan_status=scan, uploaded_by=ctx.user)
    db.add(ev)
    db.flush()
    audit.record(db, ctx, "evidence", ev.id, "upload", None,
                 {"entity_type": entity_type, "entity_id": entity_id, "evidence_type": evidence_type,
                  "sha256": ev.sha256, "size": ev.size, "scan": scan,
                  **({"exit_case_id": entity_id} if entity_type == "exit_case" else {})})
    return ev


# ------------------------------------------------------------------ reports

def missing_evidence(db: Session, ctx: Ctx, max_rating: float = 2.0) -> list[dict]:
    """People rated at or below `max_rating` with no documented review in the latest closed cycle and no PIP."""
    latest = db.scalar(select(ReviewCycle).where(ReviewCycle.org_id == ctx.org_id, ReviewCycle.status == "closed")
                       .order_by(ReviewCycle.period_end.desc()).limit(1))
    out = []
    for e in db.scalars(visible_query(ctx).where(Employee.performance_rating <= max_rating)):
        has_pip = db.scalar(select(Pip.id).where(Pip.employee_id == e.id).limit(1)) is not None
        rev = db.scalar(select(Review).where(Review.employee_id == e.id, Review.cycle_id == latest.id)) if latest else None
        documented = bool(rev and (rev.manager_comment or "").strip())
        if not has_pip and not documented:
            out.append({"employee_id": e.id, "employee_code": e.employee_code, "full_name": e.full_name,
                        "department": e.department, "performance_rating": e.performance_rating,
                        "missing": "no PIP and no documented review in the latest cycle"})
    return out
