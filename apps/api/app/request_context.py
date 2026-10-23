"""Per-request ID, attached to audit entries and returned as X-Request-ID."""

import uuid
from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return request_id.get()


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
