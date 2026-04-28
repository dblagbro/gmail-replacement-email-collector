# Setup

This walkthrough assumes you've already installed via [Docker](../README.md#quick-start-docker) or [Windows .exe](../README.md#quick-start-windows).

## 1. First-run password

Open http://localhost:8077 (or whatever your URL is). You'll see the **First-time setup** page.

Pick a password — this protects the web UI itself. Minimum 8 characters. Save it somewhere; there's no recovery short of deleting the database.

## 2. Connect Gmail (OAuth)

Click **Gmail OAuth** in the top navigation, then **Connect a new Gmail account**.

Choose either:

- **Built-in app** — uses the project's shared OAuth client. You'll be redirected to Google to approve. The consent screen lists the permissions: *insert messages*, *manage labels*, *modify messages* (only used if you choose to delete-from-Gmail-too).
- **Bring your own** — upload a `client_secret.json` you created in your own Google Cloud project. See [GMAIL_OAUTH.md](GMAIL_OAUTH.md).

After approval Google redirects back to the app and your Gmail address shows in the **Connected accounts** list.

## 3. Add a source IMAP account

Dashboard → **+ Add account**.

| Field | Notes |
|---|---|
| Display name | Any label, e.g. "Earthlink" |
| IMAP host | See [PROVIDERS.md](PROVIDERS.md) — for Earthlink: `imap.earthlink.net` |
| Port | Almost always `993` (SSL) |
| Username | Usually your full email address |
| Password | Your IMAP password — *not* your Gmail password. Most modern providers require an **app-specific password** (see provider docs). |
| Folder | `INBOX` is normal |
| Polling mode | **IMAP IDLE (recommended)** — pushes new mail in seconds. Periodic poll is a fallback for servers that don't support IDLE. |
| Destination Gmail | Pick the OAuth account you connected in step 2 |
| Auto-apply label | Optional — e.g. `earthlink` so all forwarded mail is labeled |

Click **Save**. The worker starts immediately. If anything's wrong (bad password, wrong host) it'll show in the **Status** column on the dashboard.

## 4. Test it

Send a test email to the IMAP account from any other address. Within 5–15 seconds it should appear in your Gmail inbox with:
- ✅ Original `From:` (not your IMAP account)
- ✅ Original `Date:`
- ✅ Original `Subject:`
- ✅ Any attachments
- ✅ Threading preserved (replies will thread normally)

Check **Archive** in the UI for a local copy + the activity log on the dashboard.

## 5. Tune retention

Settings → set the number of days to keep the local `.eml` archive (default 30). Past that, files are auto-deleted on the next sweep (every 6 hours). Manual sweep button is on the dashboard.

## Done

The service runs forever in the background. Add more accounts as needed. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if anything's wrong.
