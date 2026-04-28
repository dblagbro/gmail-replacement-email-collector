# Gmail Replacement Email Collector

> A drop-in replacement for Gmail's "Check mail from other accounts" / **Gmailify**, which Google [is shutting down in 2026](https://support.google.com/mail/answer/16604719?hl=en).

Polls your other email accounts (Earthlink, Yahoo, Outlook, Comcast, AOL, iCloud, any IMAP/POP3 host) and **inserts** the messages directly into your Gmail inbox via the official Gmail API — preserving the original `From:`, `Date:`, `Message-ID:`, and all headers exactly as sent.

> **Why not just SMTP-forward?** Forwarding rewrites the `From:` header (or breaks DKIM/SPF/DMARC if it doesn't), gets caught by Gmail's spam filter, and loses threading. This tool uses [`users.messages.insert`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/insert) — the same mechanism Gmailify used internally — so messages appear in your inbox identical to having been sent there directly.

---

## Features

| | |
|---|---|
| ⚡ Real-time | IMAP IDLE — new mail appears in Gmail within seconds |
| 🔒 Preserves headers | Original `From:`, `Date:`, `Message-ID:` exactly preserved |
| 🛡️ No SPF/DKIM/DMARC issues | Bypasses delivery pipeline entirely |
| 📥 Local archive | Every message saved as `.eml` for N configurable days |
| 🔍 Browse / search | Full archive browser in the web UI |
| 🏷️ Auto-label | Optionally label inserted mail (e.g. `earthlink`) |
| 🛂 Sender rules | Skip newsletters or apply per-sender labels |
| 🔁 Multi-account | Connect multiple POP/IMAP sources → multiple Gmail destinations |
| 🔐 Encrypted secrets | IMAP passwords + OAuth tokens encrypted at rest (Fernet) |
| 🐳 Docker | One-command deploy with `docker compose` |
| 🪟 Windows | Single-file `.exe` for non-technical users — no Docker, no Python |

---

## Quick start (Docker)

```bash
docker run -d \
  --name gmail-email-collector \
  -p 8077:8077 \
  -v "$PWD/data":/data \
  --restart unless-stopped \
  dblagbro/gmail-replacement-email-collector:1.0
```

Then open http://localhost:8077 — set your UI password, connect Gmail OAuth, add an IMAP source.

Or use the included `docker-compose.example.yml`.

## Quick start (Windows)

1. Download `EmailCollector.exe` from the [latest release](https://github.com/dblagbro/gmail-replacement-email-collector/releases/latest)
2. Double-click. SmartScreen may say "Windows protected your PC" — click **More info → Run anyway** (the binary is unsigned during early-access; signed builds coming with v1.1)
3. A tray icon appears, your browser opens to http://127.0.0.1:8077
4. Set a UI password, connect Gmail (OAuth), add your IMAP source
5. Done. The tray icon stays in the corner; right-click → Quit to stop

Data lives in `%APPDATA%\EmailForwarder\`.

---

## Setup walkthrough

### 1. Connect a Gmail destination

Click **Gmail OAuth → Connect a new Gmail account**. Two modes:

- **Built-in app** (easiest): uses this project's verified Google OAuth client. *(Note: pending Google verification — until approved, the consent screen will say "this app isn't verified" and you'll need to click Advanced → "Go to ... (unsafe)" once. Your data is yours, the app does not phone home.)*
- **BYO Google Cloud project**: create your own OAuth client and upload the `client_secret.json`. See [docs/GMAIL_OAUTH.md](docs/GMAIL_OAUTH.md) for the 5-minute walkthrough. **Maximum privacy** — Google grants tokens to *your* Google Cloud project, not anyone else's.

### 2. Add an IMAP source

Click **+ Add account**. Common providers:

| Provider | IMAP host | Port |
|---|---|---|
| Earthlink | `imap.earthlink.net` | 993 |
| Yahoo | `imap.mail.yahoo.com` | 993 |
| Outlook.com / Hotmail | `outlook.office365.com` | 993 |
| AOL | `imap.aol.com` | 993 |
| iCloud | `imap.mail.me.com` | 993 |
| Comcast | `imap.comcast.net` | 993 |

Most providers now require an **app-specific password** rather than your account password — see [docs/PROVIDERS.md](docs/PROVIDERS.md).

### 3. Verify

Send a test email to your other account. Within seconds it appears in your Gmail inbox with the *original* sender address. Check the **Activity log** on the dashboard if anything goes wrong.

---

## Configuration

All runtime settings live in the web UI. A few startup defaults can be overridden via environment variables:

| Env var | Default | Purpose |
|---|---|---|
| `URL_PREFIX` | (empty) | Set if hosting behind nginx at a subpath, e.g. `/email-collector` |
| `PORT` | `8077` | HTTP port |
| `DEFAULT_RETENTION_DAYS` | `30` | Days to keep local `.eml` archive |
| `BUILTIN_OAUTH_CLIENT_ID` | (empty) | Built-in OAuth app client ID |
| `BUILTIN_OAUTH_CLIENT_SECRET` | (empty) | Built-in OAuth app client secret |
| `EMAIL_FORWARDER_DATA_DIR` | `/data` (Docker), `%APPDATA%\EmailForwarder` (Windows) | Where to store DB + archive |

---

## Documentation

- [SETUP.md](docs/SETUP.md) — first-run walkthrough with screenshots
- [GMAIL_OAUTH.md](docs/GMAIL_OAUTH.md) — built-in app vs BYO Google Cloud project
- [EARTHLINK.md](docs/EARTHLINK.md) — Earthlink-specific IMAP gotchas
- [PROVIDERS.md](docs/PROVIDERS.md) — tested settings for major providers
- [RETENTION.md](docs/RETENTION.md) — how the local archive + purge works
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common issues
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — for contributors

---

## Why this exists

In January 2026, Google announced ([source](https://support.google.com/mail/answer/16604719?hl=en)) that Gmail's "Check mail from other accounts" feature (which polls your POP3 / IMAP / Yahoo / Outlook / etc. accounts and brings the mail into Gmail) is being **shut down in January 2027**, with no new setups allowed after Q1 2026.

Millions of people rely on this to consolidate their email into one inbox. The official suggested alternatives — desktop email clients, native forwarding — either don't preserve the sender, lose Gmail's spam filter and search, or require maintaining multiple inboxes.

This project replaces the missing functionality using the documented Gmail API, with the same UX Gmailify provided.

---

## Privacy

- **All data stays on your machine.** Nothing is sent anywhere except: (a) IMAP fetch from your provider, (b) Gmail API insert into your mailbox.
- **OAuth tokens never leave your device.** The "built-in app" mode means *Google* grants tokens to a Google Cloud project owned by the project author, but the tokens themselves are stored only on your machine and used only by your local copy. The author has no access.
- **For maximum privacy**, use BYO mode (your own Google Cloud project). Then nothing about your Gmail consent flow ever touches the project author's account.

See [docs/PRIVACY.md](docs/PRIVACY.md) for details.

---

## License

MIT — see [LICENSE](LICENSE).
