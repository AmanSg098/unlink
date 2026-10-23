"""Development mail preview on http://localhost:8025 (started by dev.sh).

Shows messages captured by the capture provider. Refuses to run outside APP_ENV=development.
Usage: uv run uvicorn app.mailview:app --port 8025
"""

from html import escape

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.config import IS_DEV
from app.db import SessionLocal
from app.models import CapturedMail

app = FastAPI(title="Unlink mail capture", docs_url=None, redoc_url=None)

STYLE = """<style>body{font:14px system-ui;margin:0;background:#111318;color:#e8e8ee}
a{color:#9aa4ff;text-decoration:none}main{max-width:960px;margin:0 auto;padding:24px}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #2a2c33;text-align:left}
pre{white-space:pre-wrap;background:#1a1c22;padding:16px;border-radius:8px}.muted{color:#8b8d97}
.banner{background:#2b2410;border:1px solid #6b5a1e;padding:8px 12px;border-radius:8px;margin-bottom:16px}</style>"""


def _guard():
    if not IS_DEV:
        raise HTTPException(404)


@app.get("/", response_class=HTMLResponse)
def inbox():
    _guard()
    with SessionLocal() as db:
        rows = db.scalars(select(CapturedMail).order_by(CapturedMail.id.desc()).limit(300)).all()
    body = "".join(
        f"<tr><td class=muted>{m.created_at:%Y-%m-%d %H:%M}</td><td>{escape(', '.join(m.to))}</td>"
        f"<td><a href='/m/{m.id}'>{escape(m.subject)}</a></td><td class=muted>{len(m.attachments)}</td></tr>"
        for m in rows)
    return (f"<!doctype html><title>Mail capture</title>{STYLE}<main><h1>Captured mail</h1>"
            "<div class=banner>Development only. These messages were captured and never delivered.</div>"
            f"<table><tr><th>When</th><th>To</th><th>Subject</th><th>Files</th></tr>{body}</table></main>")


@app.get("/m/{mail_id}", response_class=HTMLResponse)
def message(mail_id: int):
    _guard()
    with SessionLocal() as db:
        m = db.get(CapturedMail, mail_id)
    if m is None:
        raise HTTPException(404)
    files = "".join(f"<li>{escape(a['filename'])} <span class=muted>({a['size']} bytes)</span></li>"
                    for a in m.attachments)
    return (f"<!doctype html><title>{escape(m.subject)}</title>{STYLE}<main><a href='/'>← Inbox</a>"
            f"<h2>{escape(m.subject)}</h2><p class=muted>To: {escape(', '.join(m.to))} · {m.created_at}</p>"
            f"<pre>{escape(m.text)}</pre>{'<h3>Attachments</h3><ul>' + files + '</ul>' if files else ''}</main>")
