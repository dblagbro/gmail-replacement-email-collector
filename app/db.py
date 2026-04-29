"""SQLite schema + helpers."""
from __future__ import annotations
import sqlite3
import contextlib
from datetime import datetime, timezone
from typing import Any, Iterator

from app.paths import DB_PATH, ensure_dirs


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  imap_host TEXT NOT NULL,
  imap_port INTEGER NOT NULL DEFAULT 993,
  imap_username TEXT NOT NULL,
  imap_password_enc TEXT NOT NULL,
  imap_folder TEXT NOT NULL DEFAULT 'INBOX',
  use_ssl INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  poll_mode TEXT NOT NULL DEFAULT 'idle',
  poll_interval_sec INTEGER NOT NULL DEFAULT 300,
  gmail_label TEXT,
  destination_gmail TEXT,
  post_fetch_action TEXT NOT NULL DEFAULT 'keep',
  created_at TEXT NOT NULL,
  last_check_at TEXT,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  message_id TEXT,
  imap_uid INTEGER,
  from_addr TEXT,
  to_addr TEXT,
  subject TEXT,
  msg_date TEXT,
  size_bytes INTEGER,
  has_attachments INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  gmail_msg_id TEXT,
  error TEXT,
  eml_path TEXT,
  inserted_at TEXT NOT NULL,
  archive_until TEXT,
  UNIQUE(account_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_account_inserted ON messages(account_id, inserted_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_archive_until ON messages(archive_until);

CREATE TABLE IF NOT EXISTS settings_kv (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  match_field TEXT NOT NULL,
  match_pattern TEXT NOT NULL,
  action TEXT NOT NULL,
  action_arg TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS oauth (
  gmail_account TEXT PRIMARY KEY,
  client_id_enc TEXT,
  client_secret_enc TEXT,
  refresh_token_enc TEXT,
  access_token_enc TEXT,
  token_expiry TEXT,
  scopes TEXT,
  use_builtin_app INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  level TEXT NOT NULL,
  account_id INTEGER,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    c = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        # Lightweight migrations for columns added after v1.0.0
        cols = {r["name"] for r in c.execute("PRAGMA table_info(accounts)").fetchall()}
        if "post_fetch_action" not in cols:
            c.execute("ALTER TABLE accounts ADD COLUMN post_fetch_action TEXT NOT NULL DEFAULT 'keep'")


# ----- settings_kv helpers -----

def get_setting(key: str, default: str | None = None) -> str | None:
    with conn() as c:
        row = c.execute("SELECT value FROM settings_kv WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str | None) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO settings_kv(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def all_settings() -> dict[str, str]:
    with conn() as c:
        rows = c.execute("SELECT key, value FROM settings_kv").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ----- accounts helpers -----

def list_accounts() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM accounts ORDER BY id").fetchall()


def get_account(account_id: int) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()


def create_account(**fields: Any) -> int:
    fields.setdefault("created_at", now_iso())
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    with conn() as c:
        cur = c.execute(f"INSERT INTO accounts({cols}) VALUES({placeholders})", tuple(fields.values()))
        return int(cur.lastrowid)


def update_account(account_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE accounts SET {sets} WHERE id=?", (*fields.values(), account_id))


def delete_account(account_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def update_account_status(account_id: int, error: str | None) -> None:
    with conn() as c:
        c.execute(
            "UPDATE accounts SET last_check_at=?, last_error=? WHERE id=?",
            (now_iso(), error, account_id),
        )


# ----- messages helpers -----

def message_seen(account_id: int, message_id: str) -> bool:
    with conn() as c:
        row = c.execute(
            "SELECT 1 FROM messages WHERE account_id=? AND message_id=?",
            (account_id, message_id),
        ).fetchone()
    return row is not None


def insert_message(**fields: Any) -> int:
    fields.setdefault("inserted_at", now_iso())
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" * len(fields))
    with conn() as c:
        cur = c.execute(f"INSERT INTO messages({cols}) VALUES({placeholders})", tuple(fields.values()))
        return int(cur.lastrowid)


def list_messages(account_id: int | None = None, limit: int = 100, offset: int = 0,
                  search: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT m.*, a.name AS account_name FROM messages m JOIN accounts a ON a.id=m.account_id"
    where, params = [], []
    if account_id is not None:
        where.append("m.account_id=?")
        params.append(account_id)
    if search:
        like = f"%{search}%"
        where.append("(m.subject LIKE ? OR m.from_addr LIKE ? OR m.to_addr LIKE ?)")
        params.extend([like, like, like])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY m.inserted_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with conn() as c:
        return c.execute(sql, tuple(params)).fetchall()


def get_message(msg_id: int) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute(
            "SELECT m.*, a.name AS account_name FROM messages m "
            "JOIN accounts a ON a.id=m.account_id WHERE m.id=?",
            (msg_id,),
        ).fetchone()


def delete_message(msg_id: int) -> str | None:
    """Delete from DB. Returns the eml_path so caller can also unlink the file."""
    with conn() as c:
        row = c.execute("SELECT eml_path FROM messages WHERE id=?", (msg_id,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
        return row["eml_path"]


def messages_to_purge(now_ts: str) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT id, eml_path FROM messages WHERE archive_until IS NOT NULL AND archive_until < ?",
            (now_ts,),
        ).fetchall()


def stats() -> dict[str, int]:
    with conn() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        ok = c.execute("SELECT COUNT(*) AS n FROM messages WHERE status='inserted'").fetchone()["n"]
        failed = c.execute("SELECT COUNT(*) AS n FROM messages WHERE status='failed'").fetchone()["n"]
        skipped = c.execute("SELECT COUNT(*) AS n FROM messages WHERE status='skipped'").fetchone()["n"]
    return {"total": total, "inserted": ok, "failed": failed, "skipped": skipped}


# ----- activity log -----

def log_activity(level: str, message: str, account_id: int | None = None) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO activity(ts, level, account_id, message) VALUES(?,?,?,?)",
            (now_iso(), level, account_id, message),
        )


def recent_activity(limit: int = 100) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT a.*, ac.name AS account_name FROM activity a "
            "LEFT JOIN accounts ac ON ac.id=a.account_id "
            "ORDER BY a.ts DESC LIMIT ?",
            (limit,),
        ).fetchall()


# ----- oauth helpers -----

def get_oauth(gmail_account: str) -> sqlite3.Row | None:
    with conn() as c:
        return c.execute("SELECT * FROM oauth WHERE gmail_account=?", (gmail_account,)).fetchone()


def upsert_oauth(gmail_account: str, **fields: Any) -> None:
    fields.setdefault("created_at", now_iso())
    existing = get_oauth(gmail_account)
    if existing:
        sets = ", ".join(f"{k}=?" for k in fields)
        with conn() as c:
            c.execute(
                f"UPDATE oauth SET {sets} WHERE gmail_account=?",
                (*fields.values(), gmail_account),
            )
    else:
        fields["gmail_account"] = gmail_account
        cols = ", ".join(fields.keys())
        placeholders = ", ".join("?" * len(fields))
        with conn() as c:
            c.execute(f"INSERT INTO oauth({cols}) VALUES({placeholders})", tuple(fields.values()))


def list_oauth_accounts() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM oauth ORDER BY gmail_account").fetchall()


def delete_oauth(gmail_account: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM oauth WHERE gmail_account=?", (gmail_account,))
