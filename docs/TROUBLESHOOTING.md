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

## "OAuth consent screen says 'Google hasn't verified this app'"

Expected. `gmail.insert` and `gmail.modify` are Google *restricted* scopes; the warning stays until an app passes Google's restricted-scope review (a paid yearly CASA security assessment), whether it's the built-in app or your own BYO project. Click **Advanced → Go to … (unsafe)** to continue. You only see it when you connect, not during normal running.

## "I have to re-authorize every week"

Your OAuth app is in **Testing** mode: Google cancels Testing grants 7 days after you connect. Open Google Cloud Console → **Google Auth Platform → Audience → Publish app**, then reconnect once. Published ("In production") grants last until revoked. See [GMAIL_OAUTH.md](GMAIL_OAUTH.md).

If you're on v1.0.3 or older, the reminder email itself was the problem: it fired every 5.5 days based on the grant's age even when Google still accepted it. v1.0.4 only reminds when Google actually rejects the grant.

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
