# Retention & local archive

Every successfully forwarded message is saved to disk as an `.eml` file before insertion into Gmail. This gives you:

- A local backup if Gmail goes down or you ever want to migrate away
- A searchable record (UI provides search by subject/from/to)
- Forensic trail (was a message ever fetched and inserted? when?)

## How it works

1. **Fetch** — IMAP worker pulls a new message
2. **Store** — raw RFC822 bytes written to `<data>/eml/YYYY/MM/<timestamp>-acct<n>-<msgid>.eml`
3. **Insert** — Gmail API `messages.insert` called
4. **Record** — DB row created with `archive_until = now + retention_days`
5. **Sweep** — every 6 hours (configurable), the sweeper deletes any `.eml` whose `archive_until` has passed and removes the DB row

## Configuration

Settings page → **Retention (days for local .eml archive)** → save.

Changes apply to *new* messages only. Existing messages keep their original `archive_until`. To shorten retroactively, run **Run sweep now** after lowering the value (it'll re-evaluate based on current setting? No — `archive_until` was stamped at insert time. To force purge of older messages immediately, you can manually delete from the Archive page or use the SQLite CLI).

## Disk usage

Roughly: `daily_message_count * average_size * retention_days`.

Example: 50 messages/day × 100 KB × 30 days ≈ 150 MB. Attachments dominate — a single 25 MB PDF eats most of that.

## Manual deletion

Archive → click any message → **Delete**. Optional checkbox: "Also move Gmail copy to Trash" (uses `gmail.modify` scope).

## Disabling the archive entirely

Set `retention_days` to `1` and run sweep daily — that's the minimum. The Gmail copy is unaffected (Gmail keeps it forever per your normal Gmail settings).

## Backup

To back up the archive, just `tar -czf eml-backup.tar.gz <data>/eml/`. The `.eml` files are standard RFC822, openable by any mail client.

The DB at `<data>/collector.db` is also worth backing up — it has your account configurations and OAuth tokens (encrypted with `secret.key`, also in `<data>`).
