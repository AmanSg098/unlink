"""Append-only, hash-chained audit log.

Each entry stores the hash of the previous entry in the same organisation, so editing or removing
an entry breaks the chain. `verify_chain` recomputes it. The ORM and database triggers also refuse
UPDATE/DELETE on the table.
"""

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.crypto import canonical_json, content_hash
from app.models import AuditLog, utcnow
from app.request_context import current_request_id

if TYPE_CHECKING:
    from app.deps import Ctx

GENESIS = "0" * 64


def _ts(dt: datetime) -> str:
    """Timezone-independent timestamp text (SQLite drops tzinfo on round trip)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _entry_hash(e: AuditLog) -> str:
    return content_hash({
        "org_id": e.org_id, "actor": e.actor, "created_at": _ts(e.created_at), "entity_type": e.entity_type,
        "entity_id": e.entity_id, "action": e.action, "before": e.before, "after": e.after,
        "justification": e.justification, "request_id": e.request_id, "prev_hash": e.prev_hash,
    })


def record(
    db: Session,
    ctx: "Ctx",
    entity_type: str,
    entity_id: int | None,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
    justification: str | None = None,
) -> AuditLog:
    return record_raw(db, ctx.org_id, ctx.user, entity_type, entity_id, action, before, after, justification)


def _jsonable(v: dict | None) -> dict | None:
    """Dates, decimals etc. become strings, so what's stored is exactly what's hashed."""
    return None if v is None else json.loads(canonical_json(v))


def record_raw(db: Session, org_id: int, actor: str, entity_type: str, entity_id: int | None, action: str,
               before: dict | None = None, after: dict | None = None, justification: str | None = None) -> AuditLog:
    before, after = _jsonable(before), _jsonable(after)
    db.flush()  # make earlier entries in this transaction visible to the chain lookup
    prev = db.scalar(select(AuditLog.hash).where(AuditLog.org_id == org_id).order_by(AuditLog.id.desc()).limit(1))
    entry = AuditLog(
        org_id=org_id, actor=actor, created_at=utcnow(), entity_type=entity_type, entity_id=entity_id,
        action=action, before=before, after=after, justification=justification,
        request_id=current_request_id(), prev_hash=prev or GENESIS, hash="",
    )
    entry.hash = _entry_hash(entry)
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, org_id: int) -> dict:
    """Recompute every hash in order. Returns {ok, checked, first_bad_id}."""
    prev = GENESIS
    checked = 0
    for e in db.scalars(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.id)):
        checked += 1
        if e.prev_hash != prev or _entry_hash(e) != e.hash:
            return {"ok": False, "checked": checked, "first_bad_id": e.id}
        prev = e.hash
    return {"ok": True, "checked": checked, "first_bad_id": None}


def for_entity(db: Session, ctx: "Ctx", entity_type: str, entity_id: int, related: tuple[str, ...] = (),
               limit: int = 2000) -> list[AuditLog]:
    """Entries for an entity plus related entries that reference it in `after` (e.g. plan_id)."""
    key = f"{entity_type}_id"
    rows = db.scalars(
        select(AuditLog).where(AuditLog.org_id == ctx.org_id,
                               or_(AuditLog.entity_type == entity_type, AuditLog.entity_type.in_(related)))
        .order_by(AuditLog.id.desc())
    ).all()
    return [a for a in rows
            if (a.entity_type == entity_type and a.entity_id == entity_id)
            or (a.entity_type in related and (a.after or {}).get(key) == entity_id)][:limit]
