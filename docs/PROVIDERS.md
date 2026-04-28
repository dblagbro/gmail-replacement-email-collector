# Provider-specific IMAP settings

All providers below use **port 993 with SSL/TLS** unless noted. Most modern providers require an **app-specific password** (not your account password) — links provided.

| Provider | IMAP host | Notes |
|---|---|---|
| **Earthlink** | `imap.earthlink.net` | Use mailbox password. See [EARTHLINK.md](EARTHLINK.md). |
| **Yahoo Mail** | `imap.mail.yahoo.com` | App password required: https://login.yahoo.com/account/security |
| **Outlook.com / Hotmail / Live** | `outlook.office365.com` | App password required if 2FA enabled: https://account.live.com/proofs/AppPassword |
| **Office 365 / Microsoft 365** | `outlook.office365.com` | OAuth-only at most tenants; basic IMAP often disabled. Check with admin. |
| **AOL** | `imap.aol.com` | App password required: https://login.aol.com/account/security |
| **iCloud** | `imap.mail.me.com` | App password required: https://appleid.apple.com → Sign-In and Security |
| **Comcast / Xfinity** | `imap.comcast.net` | Enable "third-party access" in Xfinity email settings |
| **Verizon (now AOL)** | `imap.aol.com` | Verizon migrated to AOL; same as AOL |
| **AT&T (now Yahoo)** | `imap.mail.att.net` | App password required (via AT&T account portal) |
| **Cox** | `imap.cox.net` | Use mailbox password |
| **Charter / Spectrum** | `mobile.charter.net` | Use mailbox password |
| **Mail.com** | `imap.mail.com` | App password recommended |
| **GMX** | `imap.gmx.com` | Enable POP3/IMAP in GMX settings first |
| **Fastmail** | `imap.fastmail.com` | App password required |
| **ProtonMail** | (requires Proton Bridge) | Set host/port to bridge's local listener |
| **Tutanota** | (no IMAP) | Not supported — Tuta blocks third-party clients |
| **Generic** | _(your provider's IMAP host)_ | Most ISPs publish their IMAP settings; search "<provider> IMAP settings" |

## Testing the connection

If a provider isn't listed here or your settings aren't working, use this command to test the IMAP login from your terminal:

```bash
openssl s_client -connect imap.example.com:993 -crlf
```

After it connects, type:
```
a login your@email.com yourpassword
a list "" "*"
a logout
```

If `a login` returns `OK`, your credentials work. If `a list` returns folders, the connection is fully functional and Email Collector should work too.

## Adding a new provider to this list

PRs welcome. Edit this file and submit. Include host, port, auth notes, and any gotchas.
