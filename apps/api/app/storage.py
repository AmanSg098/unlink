"""Encrypted file storage on local disk (data/files). Keys are opaque; contents are AES-GCM encrypted."""

import uuid

from app.config import FILES_DIR
from app.crypto import decrypt_bytes, encrypt_bytes


def save(org_id: int, data: bytes) -> str:
    key = f"{org_id}/{uuid.uuid4().hex}.bin"
    path = FILES_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_bytes(data))
    return key


def load(key: str) -> bytes:
    return decrypt_bytes((FILES_DIR / key).read_bytes())
