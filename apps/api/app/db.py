import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

API_DIR = Path(__file__).resolve().parent.parent

# SQLite for the MVP (no Docker). Point DATABASE_URL at Postgres later, e.g.
# postgresql+psycopg://user:pass@localhost:5432/wrp
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{API_DIR / 'data' / 'app.db'}")


def make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    eng = create_engine(url, connect_args={"check_same_thread": False} if is_sqlite else {})
    if is_sqlite:

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
