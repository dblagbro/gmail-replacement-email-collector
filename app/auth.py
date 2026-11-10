"""Password authentication and expiring, revocable browser sessions."""
from __future__ import annotations
import hashlib
import secrets
import time
import bcrypt
from app import db
from app.config import SESSION_LIFETIME_HOURS

SESSION_KEY = "ef_session"

def is_setup() -> bool:
    return db.get_setting("web_password_hash") is not None

def set_password(plaintext: str) -> None:
    if not 8 <= len(plaintext.encode()) <= 72:
        raise ValueError("Password must be 8 to 72 UTF-8 bytes")
    h = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt())
    with db.conn() as c:
        c.execute("INSERT INTO settings_kv(key,value) VALUES('web_password_hash',?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (h.decode(),))
        c.execute("DELETE FROM settings_kv WHERE key LIKE 'session:%'")

def verify_password(plaintext: str) -> bool:
    h = db.get_setting("web_password_hash")
    if not h or len(plaintext.encode()) > 72:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode(), h.encode())
    except (ValueError, TypeError):
        return False

def session_key(tok: str) -> str:
    return "session:" + hashlib.sha256(tok.encode()).hexdigest()

def new_session_token() -> str:
    tok = secrets.token_urlsafe(32)
    with db.conn() as c:
        c.execute("DELETE FROM settings_kv WHERE key LIKE 'session:%' "
                  "AND CAST(value AS REAL) <= ?", (time.time(),))
        c.execute("INSERT INTO settings_kv(key,value) VALUES(?,?)",
                  (session_key(tok), str(time.time() + SESSION_LIFETIME_HOURS * 3600)))
    return tok

def is_session_valid(tok: str | None) -> bool:
    if not tok or len(tok) > 256:
        return False
    try:
        return float(db.get_setting(session_key(tok)) or 0) > time.time()
    except (ValueError, TypeError):
        return False

def revoke_session(tok: str) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM settings_kv WHERE key=?", (session_key(tok),))
