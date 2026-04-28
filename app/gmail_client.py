"""Gmail API OAuth + messages.insert wrapper.

Why messages.insert (not SMTP forward)?
  - Original From/Date/Message-ID/headers preserved exactly as sent
  - No SPF/DKIM/DMARC mangling
  - Bypasses spam classifier (lands in Inbox)
  - Same mechanism Gmailify used internally
"""
from __future__ import annotations
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app import db
from app.config import BUILTIN_OAUTH_CLIENT_ID, BUILTIN_OAUTH_CLIENT_SECRET, GMAIL_SCOPES
from app.crypto import decrypt, encrypt

logger = logging.getLogger(__name__)


def _client_config_from_row(row) -> dict[str, Any]:
    """Build a Flow client config dict from either built-in env vars or stored BYO client."""
    if row and row["use_builtin_app"]:
        cid = BUILTIN_OAUTH_CLIENT_ID
        cs = BUILTIN_OAUTH_CLIENT_SECRET
    elif row:
        cid = decrypt(row["client_id_enc"]) or ""
        cs = decrypt(row["client_secret_enc"]) or ""
    else:
        cid, cs = BUILTIN_OAUTH_CLIENT_ID, BUILTIN_OAUTH_CLIENT_SECRET
    if not cid or not cs:
        raise RuntimeError(
            "No OAuth client configured. Either set BUILTIN_OAUTH_CLIENT_ID/SECRET "
            "or paste a client_secret.json via the UI."
        )
    return {
        "web": {
            "client_id": cid,
            "client_secret": cs,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def begin_flow(redirect_uri: str, gmail_account: str | None = None,
               use_builtin: bool = True, byo_client_json: str | None = None) -> tuple[str, str]:
    """Start OAuth — returns (auth_url, state). Persists provisional client config."""
    if not use_builtin:
        if not byo_client_json:
            raise ValueError("BYO mode requires client_secret JSON")
        data = json.loads(byo_client_json)
        cfg = data.get("web") or data.get("installed")
        if not cfg:
            raise ValueError("client_secret JSON must contain 'web' or 'installed'")
        cid, cs = cfg["client_id"], cfg["client_secret"]
        # Stash provisionally under a placeholder; real account email written after callback
        db.upsert_oauth(
            gmail_account or "__pending__",
            client_id_enc=encrypt(cid),
            client_secret_enc=encrypt(cs),
            use_builtin_app=0,
            scopes=" ".join(GMAIL_SCOPES),
        )
    else:
        db.upsert_oauth(
            gmail_account or "__pending__",
            use_builtin_app=1,
            scopes=" ".join(GMAIL_SCOPES),
        )

    row = db.get_oauth(gmail_account or "__pending__")
    flow = Flow.from_client_config(_client_config_from_row(row), scopes=GMAIL_SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return auth_url, state


def complete_flow(code: str, redirect_uri: str, pending_key: str = "__pending__") -> str:
    """Exchange code -> tokens, identify the gmail account, persist tokens. Returns the account email."""
    row = db.get_oauth(pending_key)
    if row is None:
        raise RuntimeError("OAuth flow state missing — restart the wizard")
    flow = Flow.from_client_config(_client_config_from_row(row), scopes=GMAIL_SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Identify the authenticated gmail address
    profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
    email = profile["emailAddress"]

    # Move/persist row keyed by real email
    db.upsert_oauth(
        email,
        client_id_enc=row["client_id_enc"],
        client_secret_enc=row["client_secret_enc"],
        use_builtin_app=row["use_builtin_app"],
        refresh_token_enc=encrypt(creds.refresh_token),
        access_token_enc=encrypt(creds.token),
        token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        scopes=" ".join(creds.scopes or GMAIL_SCOPES),
    )
    if pending_key != email:
        db.delete_oauth(pending_key)
    return email


def _credentials_for(gmail_account: str) -> Credentials:
    row = db.get_oauth(gmail_account)
    if row is None:
        raise RuntimeError(f"No OAuth credentials stored for {gmail_account}")
    cfg = _client_config_from_row(row)["web"]
    creds = Credentials(
        token=decrypt(row["access_token_enc"]),
        refresh_token=decrypt(row["refresh_token_enc"]),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=(row["scopes"] or " ".join(GMAIL_SCOPES)).split(),
    )
    if not creds.valid:
        creds.refresh(Request())
        db.upsert_oauth(
            gmail_account,
            access_token_enc=encrypt(creds.token),
            token_expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
    return creds


def _service(gmail_account: str):
    return build("gmail", "v1", credentials=_credentials_for(gmail_account), cache_discovery=False)


def ensure_label(gmail_account: str, label_name: str) -> str:
    """Return label id, creating it if missing."""
    svc = _service(gmail_account)
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for l in labels:
        if l["name"].lower() == label_name.lower():
            return l["id"]
    created = svc.users().labels().create(
        userId="me",
        body={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return created["id"]


def insert_raw(gmail_account: str, raw_rfc822: bytes, label_ids: list[str] | None = None) -> str:
    """Insert a raw RFC822 message into the user's inbox. Returns the Gmail message id."""
    svc = _service(gmail_account)
    body = {
        "raw": base64.urlsafe_b64encode(raw_rfc822).decode("ascii"),
        "labelIds": label_ids or ["INBOX", "UNREAD"],
    }
    try:
        resp = svc.users().messages().insert(
            userId="me",
            body=body,
            internalDateSource="dateHeader",
        ).execute()
        return resp["id"]
    except HttpError as e:
        logger.error("Gmail insert failed: %s", e)
        raise


def trash_message(gmail_account: str, gmail_msg_id: str) -> None:
    svc = _service(gmail_account)
    svc.users().messages().trash(userId="me", id=gmail_msg_id).execute()
