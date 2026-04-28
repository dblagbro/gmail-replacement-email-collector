"""Per-account IMAP worker.

Two modes:
  - 'idle' — uses IMAP IDLE for near-instant push (default, recommended)
  - 'poll' — periodic UID-based scan (configurable interval)

Both modes share the same fetch/dedupe/insert path.
"""
from __future__ import annotations
import logging
import threading
import time
from email import message_from_bytes
from email.policy import default as email_default_policy
from typing import Any

from imap_tools import MailBox, MailBoxUnencrypted, AND
from imap_tools.errors import MailboxLoginError

from app import archive, db, gmail_client, rules
from app.config import IMAP_IDLE_TIMEOUT_SEC, MAX_MESSAGE_BYTES
from app.crypto import decrypt

logger = logging.getLogger(__name__)


class AccountWorker(threading.Thread):
    def __init__(self, account_id: int):
        super().__init__(daemon=True, name=f"acct-{account_id}")
        self.account_id = account_id
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    # --- main loop ---
    def run(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            try:
                self._connect_and_run()
                backoff = 5
            except MailboxLoginError as e:
                msg = f"IMAP login failed: {e}"
                logger.error("[acct %s] %s", self.account_id, msg)
                db.update_account_status(self.account_id, msg)
                db.log_activity("error", msg, self.account_id)
                self._stop.wait(60)
            except Exception as e:
                msg = f"IMAP loop error: {e}"
                logger.exception("[acct %s] %s", self.account_id, msg)
                db.update_account_status(self.account_id, msg)
                db.log_activity("error", msg, self.account_id)
                self._stop.wait(min(backoff, 300))
                backoff = min(backoff * 2, 300)

    def _connect_and_run(self) -> None:
        a = db.get_account(self.account_id)
        if a is None or not a["enabled"]:
            self._stop.wait(30)
            return
        password = decrypt(a["imap_password_enc"]) or ""
        cls = MailBox if a["use_ssl"] else MailBoxUnencrypted
        with cls(a["imap_host"], port=a["imap_port"]).login(a["imap_username"], password, initial_folder=a["imap_folder"]) as mb:
            db.update_account_status(self.account_id, None)
            db.log_activity("info", f"Connected to {a['imap_host']} as {a['imap_username']}", self.account_id)
            # Initial sweep — process anything we missed while down
            self._process_unseen(mb, a)
            if a["poll_mode"] == "idle":
                self._idle_loop(mb, a)
            else:
                self._poll_loop(mb, a)

    # --- IDLE path ---
    def _idle_loop(self, mb, a) -> None:
        while not self._stop.is_set():
            a = db.get_account(self.account_id)
            if a is None or not a["enabled"] or a["poll_mode"] != "idle":
                return
            try:
                responses = mb.idle.wait(timeout=min(IMAP_IDLE_TIMEOUT_SEC, 60))
                if responses:
                    self._process_unseen(mb, a)
            except Exception as e:
                logger.warning("[acct %s] IDLE error, reconnecting: %s", self.account_id, e)
                return  # outer loop reconnects

    # --- poll path ---
    def _poll_loop(self, mb, a) -> None:
        while not self._stop.is_set():
            a = db.get_account(self.account_id)
            if a is None or not a["enabled"] or a["poll_mode"] != "poll":
                return
            self._process_unseen(mb, a)
            self._stop.wait(max(int(a["poll_interval_sec"]), 30))

    # --- shared processing ---
    def _process_unseen(self, mb, a) -> None:
        """Fetch UNSEEN, dedupe by Message-ID, insert into Gmail."""
        for msg in mb.fetch(AND(seen=False), mark_seen=False, bulk=False):
            mid = (msg.headers.get("message-id", ("",))[0] or msg.uid or "").strip("<>")
            if not mid:
                mid = f"no-message-id-uid-{msg.uid}"
            if db.message_seen(self.account_id, mid):
                # Mark seen on IMAP side so it doesn't keep showing up
                try:
                    mb.flag(msg.uid, "\\Seen", True)
                except Exception:
                    pass
                continue
            self._handle_one(mb, a, msg, mid)

    def _handle_one(self, mb, a, msg, mid: str) -> None:
        raw = msg.obj.as_bytes(policy=email_default_policy)
        size = len(raw)
        if size > MAX_MESSAGE_BYTES:
            self._record(a, msg, mid, raw=None, status="skipped",
                         error=f"Message too large ({size} bytes)", gmail_msg_id=None, eml_path=None)
            try:
                mb.flag(msg.uid, "\\Seen", True)
            except Exception:
                pass
            return

        action, action_arg = rules.evaluate(self.account_id, msg)
        if action == "skip":
            self._record(a, msg, mid, raw=raw, status="skipped",
                         error=f"Rule: skip ({action_arg})", gmail_msg_id=None, eml_path=None)
            try:
                mb.flag(msg.uid, "\\Seen", True)
            except Exception:
                pass
            return

        # Persist .eml first so we have it even if Gmail insert fails
        eml_path = archive.store_eml(self.account_id, mid, raw)

        # Determine label
        label_ids = ["INBOX", "UNREAD"]
        try:
            target_label = action_arg if action == "label" else a["gmail_label"]
            if target_label and a["destination_gmail"]:
                lid = gmail_client.ensure_label(a["destination_gmail"], target_label)
                label_ids.append(lid)
        except Exception as e:
            logger.warning("[acct %s] label setup failed: %s", self.account_id, e)

        try:
            gmail_id = gmail_client.insert_raw(a["destination_gmail"], raw, label_ids)
            self._record(a, msg, mid, raw=raw, status="inserted",
                         error=None, gmail_msg_id=gmail_id, eml_path=str(eml_path))
            try:
                mb.flag(msg.uid, "\\Seen", True)
            except Exception:
                pass
        except Exception as e:
            self._record(a, msg, mid, raw=raw, status="failed",
                         error=str(e), gmail_msg_id=None, eml_path=str(eml_path))
            # leave UNSEEN on IMAP so a retry will pick it up later

    def _record(self, a, msg, mid: str, *, raw: bytes | None, status: str,
                error: str | None, gmail_msg_id: str | None, eml_path: str | None) -> None:
        size = len(raw) if raw else 0
        has_attach = 1 if any(True for _ in (msg.attachments or [])) else 0
        try:
            db.insert_message(
                account_id=self.account_id,
                message_id=mid,
                imap_uid=int(msg.uid) if str(msg.uid).isdigit() else None,
                from_addr=msg.from_,
                to_addr=", ".join(msg.to or []),
                subject=msg.subject or "",
                msg_date=msg.date_str or "",
                size_bytes=size,
                has_attachments=has_attach,
                status=status,
                gmail_msg_id=gmail_msg_id,
                error=error,
                eml_path=eml_path,
                archive_until=archive.archive_until() if eml_path else None,
            )
            level = "info" if status == "inserted" else ("warn" if status == "skipped" else "error")
            db.log_activity(level, f"{status}: {msg.from_} | {msg.subject!r}", self.account_id)
        except Exception as e:
            logger.exception("[acct %s] DB record failed: %s", self.account_id, e)
