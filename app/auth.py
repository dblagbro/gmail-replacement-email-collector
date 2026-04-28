"""Web UI auth — single password (bcrypt) stored in settings_kv."""
from __future__ import annotations
import secrets

import bcrypt

from app import db


SESSION_KEY = "ef_session"


def is_setup() -> bool:
    return db.get_setting("web_password_hash") is not None


def set_password(plaintext: str) -> None:
    h = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt())
    db.set_setting("web_password_hash", h.decode())


def verify_password(plaintext: str) -> bool:
    h = db.get_setting("web_password_hash")
    if not h:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode(), h.encode())
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    tok = secrets.token_urlsafe(32)
    db.set_setting(f"session:{tok}", "1")
    return tok


def is_session_valid(tok: str | None) -> bool:
    if not tok:
        return False
    return db.get_setting(f"session:{tok}") == "1"


def revoke_session(tok: str) -> None:
    db.set_setting(f"session:{tok}", None)
