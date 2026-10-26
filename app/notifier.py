"""OAuth re-authorization reminder via SMTP.

Google stops accepting a stored Gmail grant when it is revoked, the Google
password changes, or the OAuth app is in the "Testing" publishing state (Testing
grants expire after 7 days). The user then has to re-run the OAuth wizard.

This module:
  - detects when a re-auth is needed (Google rejects the grant on refresh, or recent invalid_grant errors)
  - sends a reminder email with a one-click link to the OAuth wizard
  - rate-limits to once per 24 h so it can be safely run on a 6 h timer

It reuses the existing IMAP-account password as SMTP auth (vast majority of
mail providers accept the same creds for both), with a built-in mapping
from common IMAP hostnames to their SMTP submission endpoints.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from app import db
from app.config import URL_PREFIX
from app.crypto import decrypt

logger = logging.getLogger(__name__)


# IMAP hostname suffix → (SMTP submission host, port, STARTTLS).
# Add as needed; falls back to literal IMAP host with smtp prefix.
_SMTP_MAP: dict[str, tuple[str, int, bool]] = {
    "earthlink.net": ("smtpauth.earthlink.net", 587, True),
    "gmail.com": ("smtp.gmail.com", 587, True),
    "googlemail.com": ("smtp.gmail.com", 587, True),
    "outlook.com": ("smtp.office365.com", 587, True),
    "hotmail.com": ("smtp.office365.com", 587, True),
    "yahoo.com": ("smtp.mail.yahoo.com", 587, True),
    "aol.com": ("smtp.aol.com", 587, True),
    "icloud.com": ("smtp.mail.me.com", 587, True),
    "comcast.net": ("smtp.comcast.net", 587, True),
    "verizon.net": ("smtp.verizon.net", 587, True),
}


def _smtp_target_for(imap_host: str) -> tuple[str, int, bool]:
    h = (imap_host or "").lower()
    for suffix, target in _SMTP_MAP.items():
        if suffix in h:
            return target
    # Generic fallback: replace 'imap' with 'smtp', port 587 STARTTLS
    return (h.replace("imap", "smtp", 1), 587, True)


def _last_oauth_failure_age_hours() -> float | None:
    """Return hours since the most recent invalid_grant message, or None if none."""
    with db.conn() as c:
        row = c.execute(
            "SELECT MAX(inserted_at) AS ts FROM messages "
            "WHERE status='failed' AND error LIKE '%invalid_grant%'"
        ).fetchone()
    if not row or not row["ts"]:
        return None
    try:
        ts = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


def _rejected_grants() -> list[str]:
    """Ask Google to refresh each stored grant; return the accounts Google rejects.

    Only an explicit invalid_grant counts. Network trouble or a Google outage is
    not a reason to send a reminder.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request

    from app.gmail_client import _credentials_for

    rejected = []
    with db.conn() as c:
        accounts = [r["gmail_account"] for r in c.execute(
            "SELECT gmail_account FROM oauth WHERE refresh_token_enc IS NOT NULL AND gmail_account LIKE '%@%'")]
    for acct in accounts:
        try:
            creds = _credentials_for(acct)
            creds.refresh(Request())
        except RefreshError as e:
            if "invalid_grant" in str(e):
                rejected.append(acct)
            else:
                logger.warning("OAuth check for %s: %s", acct, e)
        except Exception as e:  # network etc. -- try again next check
            logger.warning("OAuth check for %s skipped: %s", acct, e)
    return rejected


def reminder_due() -> tuple[bool, str]:
    """Decide whether a reminder should be sent right now.

    Returns (due, reason). Due if either:
      - Google rejects a stored grant right now (invalid_grant on refresh), or
      - any failed-insert with invalid_grant has been logged in the last 24 h.

    The age of a grant alone is no reason: apps published "In production"
    keep their refresh tokens until revoked.

    Always rate-limited to 1 email per 24 h via the last_reminder_sent_at setting.
    """
    last_sent = db.get_setting("last_reminder_sent_at")
    if last_sent:
        try:
            t = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - t < timedelta(hours=24):
                return False, "rate-limited (sent within last 24 h)"
        except ValueError:
            pass

    fail_age = _last_oauth_failure_age_hours()
    if fail_age is not None and fail_age <= 24:
        return True, f"recent invalid_grant ({fail_age:.1f} h ago)"

    rejected = _rejected_grants()
    if rejected:
        return True, f"Google rejected the stored grant for {', '.join(rejected)} (invalid_grant)"

    return False, f"healthy (grants accepted, last failure {fail_age} h)"


def _build_message(account_row, public_base_url: str, reason: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = account_row["imap_username"]
    msg["To"] = db.get_setting("alert_email") or account_row["destination_gmail"]
    msg["Subject"] = "🔑 Re-authorize Gmail OAuth — Email Collector"
    body = f"""Email Collector needs you to re-authorize Gmail.

Reason: {reason}

What to do (~30 seconds):
  1. Open the OAuth wizard:  {public_base_url.rstrip('/')}{URL_PREFIX}/oauth
  2. Sign in as {account_row['destination_gmail']} and approve the same scopes
  3. Back on the dashboard, click "Retry failed (N)" on the {account_row['name']} row to replay any messages that piled up

Why this happens:
  Google no longer accepts the stored Gmail grant. This happens when access
  is revoked in your Google account, the Google password changes, or the
  OAuth app is set back to "Testing" (Testing grants expire after 7 days).

— Email Collector
"""
    msg.set_content(body)
    return msg


def send_reminder(public_base_url: str, reason: str | None = None) -> tuple[bool, str]:
    """Build + send the reminder email. Returns (sent, detail)."""
    accounts = db.list_accounts()
    if not accounts:
        return False, "no accounts configured"
    a = accounts[0]
    pw = decrypt(a["imap_password_enc"]) or ""
    if not pw:
        return False, "IMAP password not decryptable"

    host, port, starttls = _smtp_target_for(a["imap_host"])
    msg = _build_message(a, public_base_url, reason or "manual test")

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            if starttls:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            s.login(a["imap_username"], pw)
            s.send_message(msg)
    except Exception as e:
        return False, f"SMTP send failed via {host}:{port}: {e}"

    db.set_setting("last_reminder_sent_at", datetime.now(timezone.utc).isoformat())
    return True, f"reminder sent to {msg['To']} via {host}:{port}"


def check_and_send(public_base_url: str) -> None:
    """APScheduler entrypoint — run every few hours; sends only if due."""
    due, reason = reminder_due()
    if not due:
        logger.info("OAuth reminder check: not due (%s)", reason)
        return
    sent, detail = send_reminder(public_base_url, reason)
    level = "info" if sent else "error"
    db.log_activity(level, f"OAuth reminder ({reason}): {detail}")
    logger.log(logging.INFO if sent else logging.ERROR, "OAuth reminder: %s", detail)
