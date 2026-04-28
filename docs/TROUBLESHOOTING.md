# Troubleshooting

## "AUTHENTICATIONFAILED" on IMAP login

- Wrong password — most modern providers require an **app-specific password**, not your account password. See [PROVIDERS.md](PROVIDERS.md) for links.
- Provider has flagged "less secure" access — log into the provider's webmail once to clear any security prompts.
- Two-factor authentication is on without an app password — most providers won't accept your real password if 2FA is enabled.

## "Token refresh failed" / "invalid_grant"

OAuth refresh token is no longer valid. Causes:
- You revoked access at https://myaccount.google.com/permissions
- The app was removed from Google's project
- 6 months elapsed without use (Google expires unused tokens)

Fix: Gmail OAuth → Disconnect → Connect again.

## Mail isn't arriving in Gmail

- Check **Activity log** on the dashboard — most issues show there
- IMAP polling: did the IDLE connection drop? Restart the worker via Settings → Reconcile workers
- Gmail's daily insert quota — `messages.insert` is rate-limited (~1 billion quota units/day per project, ~25 units/insert). For normal usage you'll never hit it; if you somehow do, wait a few hours.
- Spam — `messages.insert` *should* skip spam classification, but if you suspect Gmail's filters are still applied, check Spam folder

## "OAuth consent screen says 'unverified'"

This is normal during early access — Google verification takes 4–6 weeks. Either:
- Click **Advanced → Go to (unsafe)** once; after that you won't see it again
- Use BYO mode (your own Google Cloud project) — see [GMAIL_OAUTH.md](GMAIL_OAUTH.md). With BYO, you're the developer of your own app, and Google trusts you implicitly.

## SmartScreen warning on Windows

Click **More info → Run anyway** once. The .exe is unsigned during early access; signed builds are coming with v1.1 once free OSS code-signing approval comes through.

## Container restarts in a loop / fails health check

Check logs: `docker logs gmail-email-collector`.

Common causes:
- Port 8077 already in use — change `PORT` env var
- Volume permissions — the container needs write access to `/data`. On Linux: `chown -R 1000:1000 ./data` before first start (or use `:rw` mount and accept root-owned data).

## Where to file bugs

GitHub issues: https://github.com/dblagbro/gmail-replacement-email-collector/issues — include:
- Mode (Docker, Windows, standalone)
- Version (Help → About in UI, or `docker inspect ...`)
- Excerpt of activity log
- Provider name (no credentials!)
