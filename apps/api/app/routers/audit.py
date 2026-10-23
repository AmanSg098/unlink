from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, reports
from app.db import get_db
from app.deps import Ctx, require
from app.models import AuditLog
from app.serialize import to_dict

router = APIRouter(tags=["audit"])
LEGAL_ADMIN = require("legal")


@router.get("/audit")
def list_audit(entity_type: str | None = None, entity_id: int | None = None, plan_id: int | None = None,
               case_id: int | None = None, actor: str | None = None, limit: int = 500,
               ctx: Ctx = Depends(LEGAL_ADMIN), db: Session = Depends(get_db)):
    if plan_id is not None:
        return [to_dict(a) for a in audit.for_entity(db, ctx, "plan", plan_id, related=("override",), limit=limit)]
    if case_id is not None:
        return [to_dict(a) for a in audit.for_entity(db, ctx, "exit_case", case_id,
                                                     related=("notice_message", "notice_draft", "fnf", "document",
                                                              "clearance", "grievance", "evidence"), limit=limit)]
    q = select(AuditLog).where(AuditLog.org_id == ctx.org_id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditLog.entity_id == entity_id)
    if actor:
        q = q.where(AuditLog.actor == actor)
    return [to_dict(a) for a in db.scalars(q.order_by(AuditLog.id.desc()).limit(min(limit, 5000)))]


@router.get("/audit/verify")
def verify(ctx: Ctx = Depends(LEGAL_ADMIN), db: Session = Depends(get_db)):
    result = audit.verify_chain(db, ctx.org_id)
    audit.record(db, ctx, "audit", None, "verify_chain", None, result)
    db.commit()
    return result


@router.get("/audit/export.json")
def export(ctx: Ctx = Depends(LEGAL_ADMIN), db: Session = Depends(get_db)):
    data = reports.audit_json(db, ctx)
    audit.record(db, ctx, "audit", None, "export_json")
    db.commit()
    return Response(data, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="unlink-audit.json"'})


@router.get("/reports/hris.csv")
def hris_export(ctx: Ctx = Depends(require("finance", "hr")), db: Session = Depends(get_db)):
    data = reports.hris_csv(db, ctx)
    audit.record(db, ctx, "report", None, "export_hris_csv")
    db.commit()
    return Response(data, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="exits.csv"'})
