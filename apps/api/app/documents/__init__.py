"""Document generation: HTML templates -> PDF (WeasyPrint), watermarked, optionally password-protected (AES-256),
stored encrypted, and sealed with a SHA-256 hash recorded in the audit log."""

import io
import secrets
import string
from datetime import date

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, storage
from app.config import TEMPLATES_DIR
from app.crypto import sha256_bytes
from app.deps import Ctx
from app.models import Document, Employee, ExitCase, FnfLine, FnfStatement, Org, Ruleset

KINDS = {
    "termination_letter": ("letter.html", "Termination letter"),
    "role_elimination_notice": ("letter.html", "Notice of role elimination"),
    "notice_letter": ("letter.html", "Notice"),
    "fnf_statement": ("fnf_statement.html", "Full and final settlement statement"),
    "relieving_letter": ("relieving_letter.html", "Relieving letter"),
    "experience_letter": ("experience_letter.html", "Experience letter"),
    "certificate_of_service": ("certificate_of_service.html", "Certificate of service"),
    "acknowledgement_form": ("acknowledgement_form.html", "Acknowledgement form"),
}

_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR / "documents"), autoescape=select_autoescape(["html"]))
_env.globals["money"] = lambda p: f"₹{p / 100:,.2f}"


class PdfUnavailable(RuntimeError):
    pass


def html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML  # native libs; imported only when needed
    except OSError as exc:
        raise PdfUnavailable("PDF engine unavailable: install pango and start the API through dev.sh") from exc
    return HTML(string=html).write_pdf()


def protect(pdf: bytes, password: str) -> bytes:
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    w.encrypt(user_password=password, owner_password=secrets.token_urlsafe(16), algorithm="AES-256")
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def base_context(db: Session, org_id: int, e: Employee, case: ExitCase | None, title: str, ref: str) -> dict:
    org = db.get(Org, org_id)
    s = org.settings or {}
    return {
        "title": title, "doc_ref": ref, "issue_date": date.today().isoformat(),
        "company_name": s.get("legal_name", org.name), "company_address": s.get("address", ""),
        "employee_name": e.full_name, "employee_code": e.employee_code, "role": e.role, "department": e.department,
        "location": e.location, "hire_date": e.hire_date.isoformat(),
        "last_working_day": (case.actual_last_day or case.last_working_day).isoformat()
        if case and (case.actual_last_day or case.last_working_day) else "-",
    }


def render(kind: str, context: dict) -> bytes:
    template, _ = KINDS[kind]
    return html_to_pdf(_env.get_template(template).render(**context))


def store(db: Session, ctx: Ctx, kind: str, title: str, pdf: bytes, employee_id: int, case_id: int | None,
          password: str | None = None) -> Document:
    data = protect(pdf, password) if password else pdf
    version = (db.scalar(select(func.max(Document.version)).where(
        Document.org_id == ctx.org_id, Document.employee_id == employee_id, Document.kind == kind)) or 0) + 1
    doc = Document(org_id=ctx.org_id, exit_case_id=case_id, employee_id=employee_id, kind=kind, version=version,
                   title=title, storage_key=storage.save(ctx.org_id, data), sha256=sha256_bytes(data),
                   password_protected=bool(password), issued_by=ctx.user)
    db.add(doc)
    db.flush()
    audit.record(db, ctx, "document", doc.id, "document_issued", None,
                 {"kind": kind, "version": version, "sha256": doc.sha256, "exit_case_id": case_id,
                  "password_protected": bool(password)})
    return doc


def fnf_context(db: Session, st: FnfStatement) -> dict:
    lines = db.scalars(select(FnfLine).where(FnfLine.statement_id == st.id).order_by(FnfLine.position)).all()
    rs = db.get(Ruleset, st.ruleset_id) if st.ruleset_id else None
    return {"fnf": st, "lines": lines, "ruleset": f"{rs.title} v{rs.version}" if rs else "no ruleset"}


def issue_for_case(db: Session, ctx: Ctx, case: ExitCase, kind: str, password: str | None = None) -> Document:
    if kind not in KINDS:
        raise HTTPException(422, f"Unknown document kind: {kind}")
    e = db.get(Employee, case.employee_id)
    _, title = KINDS[kind]
    c = base_context(db, ctx.org_id, e, case, title, f"EXIT-{case.id}-{kind.upper()[:4]}")
    if kind == "fnf_statement":
        st = db.scalar(select(FnfStatement).where(FnfStatement.exit_case_id == case.id,
                                                  FnfStatement.status.in_(("approved", "paid")))
                       .order_by(FnfStatement.version.desc()))
        if st is None:
            raise HTTPException(409, "No approved FNF statement to issue")
        c |= fnf_context(db, st)
    elif kind == "acknowledgement_form":
        c["documents"] = db.scalars(select(Document).where(Document.exit_case_id == case.id)).all()
    elif kind in ("termination_letter", "role_elimination_notice", "notice_letter"):
        raise HTTPException(422, "Notice letters are generated from approved notices when they are sent")
    try:
        pdf = render(kind, c)
    except PdfUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return store(db, ctx, kind, title, pdf, e.id, case.id, password)


def letter_pdf(db: Session, ctx: Ctx, case: ExitCase, title: str, body: str) -> bytes:
    e = db.get(Employee, case.employee_id)
    c = base_context(db, ctx.org_id, e, case, title, f"EXIT-{case.id}-NOTICE")
    c["body"] = body
    return render("notice_letter", c)
