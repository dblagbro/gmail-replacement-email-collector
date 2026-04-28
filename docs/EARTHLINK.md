# Earthlink IMAP

Earthlink's IMAP service still works as of 2026, but they've gradually tightened auth.

## Settings

| | |
|---|---|
| IMAP host | `imap.earthlink.net` |
| Port | `993` |
| Encryption | SSL/TLS |
| Username | full email address (`you@earthlink.net`) |
| Password | your Earthlink mailbox password |

## Common gotchas

- **"AUTHENTICATIONFAILED"** — Earthlink may have flagged your account for "less secure" access. Sign in to https://webmail.earthlink.net once with the same credentials to clear any prompts, then retry.
- **No app-specific passwords** — Earthlink (unlike Gmail/Yahoo/Outlook) doesn't issue app-specific passwords. You use your real mailbox password.
- **Folder names** — INBOX is the default. If you have custom folders you want to monitor, set the **Folder** field per source account.

## If Earthlink ever drops IMAP

Earthlink has talked about migrating to a new platform multiple times over the years. If/when that happens:
- The host might change (commonly `imap.mail.att.net` since AT&T owns Earthlink in some configurations)
- Port stays 993
- May require app-specific password

Update the settings in the UI; no reinstall needed.
