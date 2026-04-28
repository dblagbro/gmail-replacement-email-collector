# Gmail OAuth — built-in app vs BYO Google Cloud project

Two ways to authorize the app to insert mail into your Gmail account.

## Option A — Built-in app (easiest)

The project ships with a verified Google OAuth client. You click **Connect**, approve the scopes, done.

Pros: No setup. Works immediately.
Cons: While Google verification is pending (early releases), the consent screen will warn that "this app isn't verified". You'll need to click **Advanced → Go to (unsafe)** once. After Google approves the app (process takes 4–6 weeks), this warning goes away.

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
   - Test users: **Add users** → add your own Gmail address (since the app is in "Testing" mode, only listed test users can authorize)
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
7. You'll be redirected to Google to approve. Since your app is in "Testing" mode and you're a listed test user, no warning appears.

Done. Your Gmail account is now connected via *your* Google Cloud project.

### Re-using one BYO client for multiple Gmail accounts

The same `client_secret.json` works for any Gmail address you list as a Test User in step 4. To add another account, just go through the OAuth flow again — it'll prompt you to choose which Gmail to authorize.

### Removing access

You can revoke the app at any time at https://myaccount.google.com/permissions — find your project name, click Remove Access. The next IMAP fetch will fail with a token error; reconnect to restore.
