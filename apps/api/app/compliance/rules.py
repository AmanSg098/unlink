"""Ruleset loading (YAML -> DB, per org) and lookup."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import RULES_DIR
from app.crypto import sha256_bytes
from app.models import Employee, Rule, Ruleset


class RulesetError(ValueError):
    pass


def load_file(db: Session, org_id: int, path: Path) -> Ruleset:
    raw = path.read_bytes()
    doc = yaml.safe_load(raw)
    meta = doc["ruleset"]
    file_hash = sha256_bytes(raw)
    existing = db.scalar(select(Ruleset).where(Ruleset.org_id == org_id, Ruleset.key == meta["key"],
                                               Ruleset.version == str(meta["version"])))
    if existing:
        if existing.file_hash != file_hash:
            raise RulesetError(f"{path.name} changed but its version ({meta['version']}) did not; bump the version")
        return existing
    rs = Ruleset(org_id=org_id, key=meta["key"], version=str(meta["version"]), jurisdiction=meta["jurisdiction"],
                 title=meta["title"], source_file=str(path.relative_to(RULES_DIR.parent)), file_hash=file_hash)
    db.add(rs)
    db.flush()
    for r in doc["rules"]:
        eff = r["effective_date"]
        db.add(Rule(org_id=org_id, ruleset_id=rs.id, rule_key=r["id"], title=r["title"], category=r["category"],
                    applies_to=r.get("applies_to") or {}, value=r["value"], source=r["source"],
                    effective_date=eff if isinstance(eff, date) else date.fromisoformat(str(eff)),
                    notes=r.get("notes", "")))
    # Newest version of a key becomes the active one.
    for other in db.scalars(select(Ruleset).where(Ruleset.org_id == org_id, Ruleset.key == rs.key,
                                                  Ruleset.id != rs.id)):
        other.active = False
    db.flush()
    return rs


def load_all(db: Session, org_id: int) -> list[Ruleset]:
    return [load_file(db, org_id, p) for p in sorted(RULES_DIR.glob("*/*.yaml"))]


def active_ruleset(db: Session, org_id: int) -> Ruleset | None:
    return db.scalar(select(Ruleset).where(Ruleset.org_id == org_id, Ruleset.active.is_(True))
                     .order_by(Ruleset.id.desc()).limit(1))


@dataclass
class RuleBook:
    ruleset: Ruleset | None
    rules: dict[str, Rule]

    def get(self, key: str) -> Rule | None:
        return self.rules.get(key)

    def value(self, key: str, default=None):
        r = self.rules.get(key)
        return r.value if r is not None else default

    @property
    def unverified(self) -> list[Rule]:
        return [r for r in self.rules.values() if not r.verified_by]

    def applies(self, key: str, employee: Employee | None = None, reason_code: str | None = None) -> bool:
        r = self.rules.get(key)
        if r is None:
            return False
        a = r.applies_to or {}
        if employee is not None and a.get("employment_type") and employee.employment_type not in a["employment_type"]:
            return False
        if a.get("reason_codes") and reason_code not in a["reason_codes"]:
            return False
        return True

    def first_applicable(self, keys: list[str], employee: Employee | None = None,
                         reason_code: str | None = None) -> Rule | None:
        for k in keys:
            if self.applies(k, employee, reason_code):
                return self.rules[k]
        return None


def rulebook(db: Session, org_id: int, ruleset_id: int | None = None) -> RuleBook:
    rs = db.get(Ruleset, ruleset_id) if ruleset_id else active_ruleset(db, org_id)
    if rs is None or rs.org_id != org_id:
        return RuleBook(None, {})
    rules = db.scalars(select(Rule).where(Rule.ruleset_id == rs.id)).all()
    return RuleBook(rs, {r.rule_key: r for r in rules})
