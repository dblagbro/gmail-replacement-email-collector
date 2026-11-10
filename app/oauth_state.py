"""Single-use OAuth transactions bound to the initiating UI session."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from app import auth, db

class InvalidOAuthState(ValueError):
    pass

def _key(state: str) -> str:
    return "oauth_state:" + hashlib.sha256(state.encode()).hexdigest()

def remember(state: str, session: str, pending_key: str, verifier: str, redirect_uri: str) -> None:
    if not state or not auth.is_session_valid(session):
        raise InvalidOAuthState("Valid login required")
    db.set_setting(_key(state), json.dumps({"session": auth.session_key(session),
        "expires": time.time() + 600, "pending_key": pending_key,
        "verifier": verifier, "redirect_uri": redirect_uri}))

def consume(state: str | None, session: str | None, redirect_uri: str) -> dict:
    if not state or len(state) > 512 or not auth.is_session_valid(session):
        raise InvalidOAuthState("OAuth state missing or invalid; restart the wizard")
    with db.conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT value FROM settings_kv WHERE key=?", (_key(state),)).fetchone()
        if not row:
            raise InvalidOAuthState("OAuth transaction missing or already used")
        saved = json.loads(row[0])
        if saved["expires"] <= time.time() or saved["redirect_uri"] != redirect_uri or not hmac.compare_digest(saved["session"], auth.session_key(session)):
            raise InvalidOAuthState("OAuth transaction expired or belongs to another session")
        c.execute("DELETE FROM settings_kv WHERE key=?", (_key(state),))
    return saved
