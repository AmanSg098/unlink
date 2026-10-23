"""AES-256-GCM encryption for sensitive fields and files, plus canonical content hashing."""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import SECRET_KEY

_KEY = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"unlink", info=b"field-encryption-v1").derive(
    SECRET_KEY.encode()
)
_AES = AESGCM(_KEY)
_PREFIX = "enc1:"


def encrypt_bytes(data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + _AES.encrypt(nonce, data, None)


def decrypt_bytes(blob: bytes) -> bytes:
    return _AES.decrypt(blob[:12], blob[12:], None)


def encrypt_str(text: str | None) -> str | None:
    if text is None:
        return None
    return _PREFIX + base64.urlsafe_b64encode(encrypt_bytes(text.encode())).decode()


def decrypt_str(token: str | None) -> str | None:
    if token is None:
        return None
    if not token.startswith(_PREFIX):
        raise ValueError("value is not encrypted")
    return decrypt_bytes(base64.urlsafe_b64decode(token[len(_PREFIX):])).decode()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def content_hash(obj) -> str:
    """Stable SHA-256 of any JSON-able value. Approvals are bound to this."""
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
