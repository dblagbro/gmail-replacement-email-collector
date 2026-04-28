# Architecture (for contributors)

## High-level

```
┌──────────────────┐  IMAP IDLE  ┌──────────────────────────┐  Gmail API   ┌──────────┐
│  Source provider │ ──────────► │  AccountWorker (thread)  │ ───────────► │  Gmail   │
│  (Earthlink etc) │             │   per enabled account    │ messages.    │  Inbox   │
└──────────────────┘             └────────────┬─────────────┘ insert       └──────────┘
                                              │
                                  raw .eml + DB row
                                              │
                                              ▼
                                  ┌────────────────────────┐
                                  │  Local archive (.eml)  │
                                  │  + SQLite              │
                                  │  (retention sweeper)   │
                                  └────────────────────────┘
                                              ▲
                                              │
                                       ┌──────┴───────┐
                                       │  FastAPI UI  │
                                       │  (uvicorn)   │
                                       └──────────────┘
```

## Module layout

```
app/
├── main.py          ── FastAPI app, all HTTP routes, lifespan (DB init, worker start, scheduler)
├── auth.py          ── UI password (bcrypt) + session cookie
├── paths.py         ── Resolves data dir based on env / OS
├── config.py        ── Static config (env vars, defaults)
├── crypto.py        ── Fernet encrypt/decrypt for stored secrets
├── db.py            ── SQLite schema + helpers (one place for SQL)
├── archive.py       ── .eml store + retention sweeper
├── gmail_client.py  ── OAuth flow + messages.insert / labels / trash
├── imap_worker.py   ── Per-account IMAP IDLE loop + dedup + insert pipeline
├── forwarder.py     ── Worker registry: spawn/kill threads per account state
├── rules.py         ── Tiny pattern-match engine for sender rules
├── tray.py          ── pystray system tray (Windows/desktop only, no-op in Docker)
├── desktop.py       ── Standalone entry point: bind 127.0.0.1, open browser, tray
└── templates/       ── Jinja2 templates
```

## Key design choices

### Why FastAPI not Flask

Existing project conventions (`tax-gmail-collector`) use FastAPI; consistency matters more than the marginal differences. FastAPI's async lifespan is also a clean fit for the `apscheduler` + worker thread bootstrap.

### Why threads not asyncio for IMAP workers

`imap-tools` is sync; running it in threads is simpler than wrapping it in `asyncio.to_thread` and isolates each account's connection lifetime.

### Why SQLite

Single-file DB, no separate process, atomic dedup via `UNIQUE(account_id, message_id)`. WAL mode lets the UI read while the worker writes.

### Why store the .eml on disk separately from DB

Two reasons:
1. SQLite blob storage works but bloats the DB and slows VACUUM
2. `.eml` files are interoperable — any mail client can open them, simplifying export/migration

### Why `messages.insert` not SMTP forwarding

See README — preserves headers, no SPF/DKIM/DMARC issues, bypasses spam filter, exactly mirrors what Gmailify did.

### Encryption boundary

`secret.key` (Fernet key) protects against:
- Casual file inspection of `collector.db`
- Accidental `.db` checkin to git (you shouldn't, but)

It does NOT protect against:
- Someone with shell access to the data dir (they can read `secret.key` too)
- Memory dumps of a running container

For threat models that need more, encrypt the volume itself (LUKS, BitLocker).

## Adding a feature

Most additions touch 3 files:

1. `db.py` — add schema migration + helper
2. `main.py` — add route(s)
3. `templates/X.html` — add UI

Worker behavior changes go in `imap_worker.py`.

## Tests

`pytest` from repo root. Test data dir is set via env var.

```bash
EMAIL_FORWARDER_DATA_DIR=/tmp/ef-test pytest tests/
```

## Releasing

Tag a `v*` release on GitHub → Actions build and publish:
- `dblagbro/gmail-replacement-email-collector:1.x` Docker image (multi-arch)
- `EmailCollector.exe` attached to the GitHub Release
