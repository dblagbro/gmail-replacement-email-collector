"""Tiny rule engine: per-account sender/subject patterns -> action."""
from __future__ import annotations
import fnmatch
import re
from typing import Any

from app import db


def evaluate(account_id: int, msg: Any) -> tuple[str | None, str | None]:
    """Return (action, action_arg) for the first matching enabled rule, else (None, None)."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT * FROM rules WHERE enabled=1 AND (account_id=? OR account_id IS NULL) ORDER BY id",
            (account_id,),
        ).fetchall()
    for r in rows:
        haystack = _haystack(msg, r["match_field"])
        if _match(haystack, r["match_pattern"]):
            return r["action"], r["action_arg"]
    return None, None


def _haystack(msg: Any, field: str) -> str:
    field = (field or "from").lower()
    if field == "subject":
        return msg.subject or ""
    if field == "to":
        return ", ".join(msg.to or [])
    return msg.from_ or ""


def _match(haystack: str, pattern: str) -> bool:
    """Glob unless pattern starts with 're:' (then it's a regex)."""
    if not pattern:
        return False
    if pattern.startswith("re:"):
        try:
            return re.search(pattern[3:], haystack, re.IGNORECASE) is not None
        except re.error:
            return False
    return fnmatch.fnmatchcase(haystack.lower(), pattern.lower())
