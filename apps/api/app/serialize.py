"""Turn ORM rows into plain dicts for JSON responses."""

from sqlalchemy.orm import DeclarativeBase


def to_dict(obj: DeclarativeBase, exclude: tuple[str, ...] = (), **extra) -> dict:
    out = {c.name: getattr(obj, c.name) for c in obj.__table__.columns
           if c.name not in exclude and not c.name.endswith("_enc") and c.name not in ("password_hash", "storage_key",
                                                                                       "token_hash", "ack_token_hash")}
    out.update(extra)
    return out
