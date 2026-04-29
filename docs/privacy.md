---
title: Privacy Policy
---

# Privacy Policy

**Last updated: 2026-04-28**

## What this app collects

Gmail Replacement Email Collector ("the app") is open-source software that runs entirely on the user's own machine. It does not collect, transmit, or store any user data on any third-party server controlled by the developer.

The app makes the following network connections, all initiated and controlled by the user:

1. **IMAP/POP3 connection to user's chosen email provider** — to fetch the user's own email
2. **Google Gmail API calls** — to insert messages into the user's own Gmail mailbox via the official `gmail.users.messages.insert` endpoint

No telemetry, analytics, crash reporting, update checking, or any other phone-home behavior is included.

## OAuth scopes used

The app requests the following Google OAuth scopes against the user's Gmail account:

- `gmail.insert` — to insert messages into the user's mailbox
- `gmail.labels` — to create and apply the optional auto-label
- `gmail.modify` — to optionally move messages to Trash when the user deletes them in the app's UI

The app does not request `gmail.readonly`, `gmail.send`, `gmail.compose`, or any other scope.

## Data storage

All data is stored only on the device where the app is installed:

- **IMAP credentials** — encrypted (Fernet/AES-128-CBC + HMAC-SHA256) in a local SQLite file
- **OAuth refresh tokens** — encrypted in the same local file
- **Email content** — fetched message copies stored as `.eml` files in the user's local data directory for the user-configured retention period (default 30 days), then automatically deleted

To delete all data: uninstall the app and remove the data directory (`~/.local/share/email-forwarder/` on Linux, `%APPDATA%\EmailForwarder\` on Windows, or the mounted Docker volume).

## OAuth token revocation

Users may revoke the app's access to their Gmail account at any time at https://myaccount.google.com/permissions

## Data shared with the developer

**None.** The developer (dblagbro) has no server, no database, no analytics, and no way to see who is using the app.

When using the "built-in OAuth app" mode, the *Google Cloud project* that issues the OAuth tokens is owned by the developer. This means Google records the consent against the developer's project. However, the resulting refresh token is delivered to the user's machine and is never transmitted to the developer.

For users who want stricter isolation, the app supports "Bring Your Own Google Cloud project" mode — see [GMAIL_OAUTH.md](https://github.com/dblagbro/gmail-replacement-email-collector/blob/main/docs/GMAIL_OAUTH.md).

## Children's privacy

The app is not directed to children under 13 and does not knowingly collect data from children.

## Changes to this policy

Updates will be posted at this URL with a new "Last updated" date.

## Contact

Privacy questions: file a GitHub issue at https://github.com/dblagbro/gmail-replacement-email-collector/issues or email dblagbro@gmail.com.
