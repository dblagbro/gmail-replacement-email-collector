"""Static configuration. Runtime-changeable settings live in the DB (settings_kv)."""
import os

# URL prefix for nginx subpath mounting (e.g. "/email-forwarder")
URL_PREFIX = os.environ.get("URL_PREFIX", "").rstrip("/")

# Bind
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8077"))

# Gmail API scope: insert messages directly into mailbox + read labels for label management
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.insert",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",  # needed if user wants delete-from-Gmail action
]

# Built-in OAuth client (the verified Google app shipped with this project).
# Empty by default — set via env or the BYO-OAuth wizard until verification is approved.
BUILTIN_OAUTH_CLIENT_ID = os.environ.get("BUILTIN_OAUTH_CLIENT_ID", "")
BUILTIN_OAUTH_CLIENT_SECRET = os.environ.get("BUILTIN_OAUTH_CLIENT_SECRET", "")

# Defaults applied at first run
DEFAULT_RETENTION_DAYS = int(os.environ.get("DEFAULT_RETENTION_DAYS", "30"))
DEFAULT_ATTACH_RETENTION_DAYS = int(os.environ.get("DEFAULT_ATTACH_RETENTION_DAYS", "30"))
DEFAULT_LABEL = os.environ.get("DEFAULT_LABEL", "")  # blank = no auto-label

# Web UI session lifetime (hours)
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "24"))

# Retention sweeper interval (hours)
SWEEP_INTERVAL_HOURS = int(os.environ.get("SWEEP_INTERVAL_HOURS", "6"))

# IMAP IDLE timeout — server hint says rebind every ~29 min to avoid stale conn
IMAP_IDLE_TIMEOUT_SEC = int(os.environ.get("IMAP_IDLE_TIMEOUT_SEC", str(29 * 60)))

# Max bytes to fetch for any single message (Gmail's hard limit is ~25 MB total upload)
MAX_MESSAGE_BYTES = int(os.environ.get("MAX_MESSAGE_BYTES", str(35 * 1024 * 1024)))
