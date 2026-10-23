from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import Ctx, get_ctx
from app.serialize import to_dict
from app.workflow import approvals
from app.workflow.approvals import LINKS, TITLES

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/pending")
def pending(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Approval steps the caller can decide now (respecting separation of duties)."""
    return [to_dict(a, title=TITLES[a.entity_type], link=LINKS[a.entity_type].format(id=a.entity_id))
            for a in approvals.pending_for(db, ctx)]


@router.get("/{entity_type}/{entity_id}")
def history(entity_type: str, entity_id: int, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return [to_dict(a) for a in approvals.history(db, ctx.org_id, entity_type, entity_id)]
