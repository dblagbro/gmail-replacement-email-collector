"""At-rest encryption for stored secrets (IMAP passwords, OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC-SHA256). Key is generated on first run and
stored in DATA_DIR/secret.key with mode 0600. This protects against casual
file inspection / accidental git commit, not against root on the host.
"""
from __future__ import annotations
import os
import stat
from cryptography.fernet import Fernet

from app.paths import SECRET_KEY_PATH, ensure_dirs


_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    ensure_dirs()
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    SECRET_KEY_PATH.write_bytes(key)
    try:
        os.chmod(SECRET_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows ACLs handled differently
    return key


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return None
    return _f().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    return _f().decrypt(ciphertext.encode("ascii")).decode("utf-8")
