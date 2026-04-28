"""Local .eml archive + retention sweeper."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db
from app.config import DEFAULT_RETENTION_DAYS
from app.paths import EML_DIR

logger = logging.getLogger(__name__)


_safe_re = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(s: str, maxlen: int = 64) -> str:
    return _safe_re.sub("_", s).strip("_")[:maxlen] or "msg"


def store_eml(account_id: int, message_id: str | None, raw: bytes) -> Path:
    """Persist raw RFC822 to disk and return path."""
    now = datetime.now(timezone.utc)
    sub = EML_DIR / f"{now:%Y}" / f"{now:%m}"
    sub.mkdir(parents=True, exist_ok=True)
    mid_safe = _safe_name(message_id or f"msg-{now.timestamp()}")
    fname = f"{now:%Y%m%dT%H%M%S}-acct{account_id}-{mid_safe}.eml"
    p = sub / fname
    p.write_bytes(raw)
    return p


def archive_until(retention_days: int | None = None) -> str:
    days = int(db.get_setting("retention_days") or DEFAULT_RETENTION_DAYS) if retention_days is None else retention_days
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


def sweep_expired() -> int:
    """Delete .eml files past their archive_until and remove DB rows. Returns count purged."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = db.messages_to_purge(now)
    purged = 0
    for r in rows:
        path = r["eml_path"]
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", path, e)
        db.delete_message(r["id"])
        purged += 1
    if purged:
        db.log_activity("info", f"Retention sweep purged {purged} archived messages")
    return purged
