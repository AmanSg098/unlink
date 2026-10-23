import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.request_context import new_request_id, request_id
from app.routers import (
    admin,
    ai,
    approvals,
    audit,
    auth,
    cases,
    fnf,
    grievances,
    home,
    kpis,
    me,
    notices,
    people,
    performance,
    plans,
    rules,
)

# Application logs carry IDs and counts only; never names, pay, ratings or leave data.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("weasyprint").setLevel(logging.WARNING)
logging.getLogger("fontTools").setLevel(logging.WARNING)

app = FastAPI(title="Unlink API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3100"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or new_request_id()
    token = request_id.set(rid[:32])
    try:
        response = await call_next(request)
    finally:
        request_id.reset(token)
    response.headers["X-Request-ID"] = rid[:32]
    return response


for r in (home, auth, admin, people, performance, kpis, plans, approvals, rules, notices, cases, fnf, grievances,
          me, audit, ai):
    app.include_router(r.router, prefix="/api")
