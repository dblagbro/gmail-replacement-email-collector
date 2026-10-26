# Gmail OAuth — built-in app vs BYO Google Cloud project

Two ways to authorize the app to insert mail into your Gmail account.

## Option A — Built-in app (easiest)

The project ships with a Google OAuth client. You click **Connect**, approve the scopes, done.

Pros: No setup. Works immediately. The app is published "In production", so the grant does not expire; you connect once.
Cons: The app's branding is verified by Google, but `gmail.insert` and `gmail.modify` are Google *restricted* scopes, and they have not been through Google's restricted-scope review (which requires a paid yearly CASA security assessment). So the consent screen says **"Google hasn't verified this app"** every time you connect. Click **Advanced → Go to … (unsafe)** to continue. Unverified apps are also limited to 100 users in total, so for anything beyond personal use, Option B is the better choice.

> **Privacy note**: even with the built-in app, your OAuth refresh token is stored *only on your machine*. The project author cannot see your mail. The "shared" thing is just the OAuth client identity; tokens themselves are private to your install.

## Option B — Bring your own Google Cloud project (maximum privacy)

You create an OAuth client in your own Google Cloud project; nothing about your consent ever touches the project author's account.

Takes about 10 minutes.

### Steps

1. Go to https://console.cloud.google.com/
2. Create a new project (top left dropdown → **New project**). Call it anything, e.g. `my-email-collector`.
3. Enable the Gmail API:
   - **APIs & Services → Library**
   - Search "Gmail API" → **Enable**
4. Configure the OAuth consent screen:
   - **APIs & Services → OAuth consent screen**
   - User type: **External** → Create
   - App name: anything
   - User support email: your email
   - Developer contact email: your email
   - **Save and Continue**
   - Scopes: **Add or Remove Scopes** → search for `gmail.insert`, `gmail.labels`, `gmail.modify` → check all three → Update → **Save and Continue**
   - Test users: **Add users** → add your own Gmail address (while the app is in "Testing" mode, only listed test users can authorize)
   - **Then publish it:** **Audience → Publishing status → Publish app → Confirm**. This matters: in "Testing" mode Google cancels the grant **7 days** after you connect, so you would have to reconnect every week. "In production" grants last until you revoke them. You don't need Google's review for your own use; you'll just see the "unverified app" warning when you connect.
5. Create the OAuth client credentials:
   - **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: anything
   - **Authorized redirect URIs**: add the URL where this app is reachable + `/oauth/callback`. Examples:
     - Local Docker: `http://localhost:8077/oauth/callback`
     - Behind nginx: `https://your-domain.com/email-collector/oauth/callback`
     - Windows: `http://127.0.0.1:8077/oauth/callback`
   - **Create**
   - Click **Download JSON** — this is your `client_secret.json`
6. In Email Collector → **Gmail OAuth → Connect new account → Bring your own → upload client_secret.json**
7. You'll be redirected to Google to approve. Because the Gmail scopes are restricted and your app isn't reviewed, Google shows **"Google hasn't verified this app"**: click **Advanced → Go to <your app> (unsafe)**. It's your own app, so this is expected.

Done. Your Gmail account is now connected via *your* Google Cloud project.

### Re-using one BYO client for multiple Gmail accounts

The same `client_secret.json` works for any Gmail address (once published; in "Testing" mode only addresses listed as Test Users in step 4). To add another account, just go through the OAuth flow again — it'll prompt you to choose which Gmail to authorize.

### Removing access

You can revoke the app at any time at https://myaccount.google.com/permissions — find your project name, click Remove Access. The next IMAP fetch will fail with a token error; reconnect to restore.

### Re-authorize reminder emails

Every few hours the app asks Google whether each stored grant still works. Only when Google answers `invalid_grant` (access revoked, Google password changed, or the OAuth app set back to "Testing") does it email you a link to reconnect, at most once a day. The age of a grant alone never triggers a reminder (before v1.0.4 it did, every 5.5 days).
