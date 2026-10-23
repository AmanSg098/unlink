"""Integration registry. Each integration is off by default and enabled per organisation by an Admin.

Implemented providers:
- hris/csv_drop      people sync from a CSV file in `inbox_path`; exit write-back to `outbox_path` (after approval)
- payroll/csv        payroll inputs via CSV upload; FNF export as CSV
- email/*            configured by environment (capture | smtp | ses); shown read-only
- ticketing/webhook  POST a JSON ticket to a URL (works with most ticketing tools' inbound webhooks)
- messaging/slack_webhook, messaging/teams_webhook  incoming-webhook notifications (no names or amounts)

Planned (listed, not implemented): Keka, Darwinbox, greytHR, Jira, ServiceNow, Freshdesk, e-signature, SAML/OIDC SSO.
"""

import json
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import decrypt_str, encrypt_str
from app.models import Integration

PROVIDERS: dict[str, dict[str, dict]] = {
    "hris": {
        "csv_drop": {"label": "CSV / SFTP drop folder", "implemented": True,
                     "config": ["inbox_path", "outbox_path"], "secrets": []},
        "keka": {"label": "Keka", "implemented": False},
        "darwinbox": {"label": "Darwinbox", "implemented": False},
        "greythr": {"label": "greytHR", "implemented": False},
    },
    "payroll": {"csv": {"label": "Payroll CSV import/export", "implemented": True, "config": ["outbox_path"],
                        "secrets": []}},
    "email": {
        "capture": {"label": "Development capture", "implemented": True, "env": True},
        "smtp": {"label": "SMTP", "implemented": True, "env": True},
        "ses": {"label": "Amazon SES (SMTP interface)", "implemented": True, "env": True},
    },
    "esign": {"generic": {"label": "E-signature", "implemented": False}},
    "ticketing": {
        "webhook": {"label": "Generic webhook", "implemented": True, "config": ["url"], "secrets": ["token"]},
        "jira": {"label": "Jira", "implemented": False},
        "servicenow": {"label": "ServiceNow", "implemented": False},
        "freshdesk": {"label": "Freshdesk", "implemented": False},
    },
    "messaging": {
        "slack_webhook": {"label": "Slack incoming webhook", "implemented": True, "config": [], "secrets": ["url"]},
        "teams_webhook": {"label": "Microsoft Teams incoming webhook", "implemented": True, "config": [],
                          "secrets": ["url"]},
    },
    "sso": {"saml": {"label": "SAML", "implemented": False}, "oidc": {"label": "OIDC", "implemented": False}},
}


def enabled_integration(db: Session, org_id: int, type_: str) -> Integration | None:
    return db.scalar(select(Integration).where(Integration.org_id == org_id, Integration.type == type_,
                                               Integration.enabled.is_(True)).limit(1))


def get_secrets(i: Integration) -> dict:
    return json.loads(decrypt_str(i.secrets_enc)) if i.secrets_enc else {}


def set_secrets(i: Integration, values: dict) -> None:
    merged = {**get_secrets(i), **{k: v for k, v in values.items() if v}}
    i.secrets_enc = encrypt_str(json.dumps(merged)) if merged else None


def post_json(url: str, payload: dict, token: str | None = None, timeout: float = 15) -> int:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - admin-configured URL
        return resp.status
