# Privacy

This document is intentionally short and direct.

## What this app does with your data

| Data | What happens |
|---|---|
| Your IMAP credentials | Encrypted (Fernet/AES-128-CBC + HMAC-SHA256) and stored only on your machine |
| OAuth tokens | Same — stored only on your machine, encrypted with the same local key |
| Email content | Fetched from your IMAP provider, sent to Gmail via the official Gmail API, and a local copy stored as `.eml` for the retention period you configure (default 30 days) |
| Telemetry | **None.** No phone-home, no analytics, no error reporting service |
| Update checks | **None.** You decide when to update |

## What "built-in OAuth app" means for privacy

When you use the built-in OAuth client (the easy mode), you're authorizing a Google Cloud project owned by the project author (`dblagbro@gmail.com`).

This means:
- The author's project is what Google records the consent against
- The OAuth refresh token Google issues is bound to the author's project's client_id
- **But the token itself is delivered to your machine and stays there**

The author cannot:
- Read your email
- See your Gmail address in any aggregate stats (no telemetry exists)
- Revoke your access (only you and Google can)

The author can:
- See in the Google Cloud Console how many *total* OAuth approvals exist (a count, no identities)
- Theoretically modify the project to add scopes — but you'd see a re-consent prompt asking for new permissions, and you could decline

If any of that bothers you, use **BYO mode** — your own Google Cloud project, your own OAuth client, no shared identity at all. See [GMAIL_OAUTH.md](GMAIL_OAUTH.md).

## Data deletion

To delete all data this app has stored:

- **Docker**: `docker rm gmail-email-collector && rm -rf ./data`
- **Windows**: uninstall + delete `%APPDATA%\EmailForwarder\`

To revoke Gmail access: https://myaccount.google.com/permissions

## License & accountability

MIT-licensed open-source software, provided "as is". Source is auditable: https://github.com/dblagbro/gmail-replacement-email-collector

Issues: https://github.com/dblagbro/gmail-replacement-email-collector/issues
Privacy questions: file an issue or email dblagbro@gmail.com.
