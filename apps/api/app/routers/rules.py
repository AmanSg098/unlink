from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.compliance.rules import RulesetError, load_all
from app.config import RULESET_MODE
from app.db import get_db
from app.deps import LEGAL, Ctx, require
from app.models import Org, Rule, Ruleset, utcnow
from app.reasons import CODES
from app.schemas import VerifyIn
from app.serialize import to_dict

router = APIRouter(tags=["rules"])
VIEW = require("legal", "hr", "finance", "approver")


@router.get("/rulesets")
def list_rulesets(ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    out = []
    for rs in db.scalars(select(Ruleset).where(Ruleset.org_id == ctx.org_id).order_by(Ruleset.id.desc())):
        rules = db.scalars(select(Rule).where(Rule.ruleset_id == rs.id)).all()
        out.append(to_dict(rs, total=len(rules), verified=sum(1 for r in rules if r.verified_by)))
    return {"mode": RULESET_MODE, "rulesets": out}


@router.get("/rulesets/{ruleset_id}")
def get_ruleset(ruleset_id: int, ctx: Ctx = Depends(VIEW), db: Session = Depends(get_db)):
    rs = db.scalar(select(Ruleset).where(Ruleset.id == ruleset_id, Ruleset.org_id == ctx.org_id))
    if rs is None:
        raise HTTPException(404, "Ruleset not found")
    rules = db.scalars(select(Rule).where(Rule.ruleset_id == rs.id).order_by(Rule.category, Rule.rule_key)).all()
    return {"ruleset": to_dict(rs), "rules": [to_dict(r) for r in rules], "mode": RULESET_MODE}


@router.post("/rulesets/reload")
def reload(ctx: Ctx = Depends(require("legal")), db: Session = Depends(get_db)):
    try:
        loaded = load_all(db, ctx.org_id)
    except RulesetError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit.record(db, ctx, "ruleset", None, "reload", None, {"versions": [f"{r.key} {r.version}" for r in loaded]})
    db.commit()
    return {"loaded": [to_dict(r) for r in loaded]}


@router.post("/rulesets/{ruleset_id}/verify")
def verify(ruleset_id: int, body: VerifyIn, ctx: Ctx = Depends(LEGAL), db: Session = Depends(get_db)):
    """Record a lawyer's verification of some or all rules (name, date, note)."""
    rs = db.scalar(select(Ruleset).where(Ruleset.id == ruleset_id, Ruleset.org_id == ctx.org_id))
    if rs is None:
        raise HTTPException(404, "Ruleset not found")
    q = select(Rule).where(Rule.ruleset_id == rs.id)
    if body.rule_ids:
        q = q.where(Rule.id.in_(body.rule_ids))
    rules = db.scalars(q).all()
    for r in rules:
        r.verified_by, r.verified_on, r.verified_note = body.verified_by, body.verified_on, body.note
    audit.record(db, ctx, "ruleset", rs.id, "verify", None,
                 {"rules": [r.rule_key for r in rules], "verified_by": body.verified_by, "verified_on": body.verified_on},
                 body.note)
    db.commit()
    return {"verified": [r.rule_key for r in rules]}


@router.get("/reasons")
def reason_codes(ctx: Ctx = Depends(require("hr", "legal", "finance", "approver", "viewer")),
                 db: Session = Depends(get_db)):
    approved = (db.get(Org, ctx.org_id).settings or {}).get("reason_wording_approvals") or {}
    return [{"code": c.code, "name": c.name, "evidence": c.evidence, "evidence_type": c.evidence_type,
             "wording": c.wording, "wording_approved": approved.get(c.code)} for c in CODES.values()]


@router.post("/reasons/{code}/approve-wording")
def approve_wording(code: str, ctx: Ctx = Depends(LEGAL), db: Session = Depends(get_db)):
    if code not in CODES:
        raise HTTPException(404, "Unknown reason code")
    org = db.get(Org, ctx.org_id)
    s = dict(org.settings or {})
    approvals = dict(s.get("reason_wording_approvals") or {})
    approvals[code] = {"by": ctx.user, "at": utcnow().isoformat(), "wording": CODES[code].wording}
    s["reason_wording_approvals"] = approvals
    org.settings = s
    audit.record(db, ctx, "reason", None, "approve_wording", None, {"code": code, "wording": CODES[code].wording})
    db.commit()
    return approvals[code]
