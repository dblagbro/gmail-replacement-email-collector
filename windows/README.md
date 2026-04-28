# Windows build

Builds a single-file `EmailCollector.exe` that runs the FastAPI server on
`http://127.0.0.1:8077`, opens your browser to the UI, and shows a tray
icon for quit/open.

## Build locally (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pystray pillow pyinstaller
cd windows
pyinstaller build.spec
# Output: ..\dist\EmailCollector.exe
```

## CI build

GitHub Actions (`.github/workflows/windows-build.yml`) builds the .exe on every
tag push and attaches it to the GitHub Release.

## SmartScreen warning

The unsigned .exe will show a Windows Defender SmartScreen warning the first
time you run it: **"Windows protected your PC"**. Click **More info →
Run anyway**. This only happens until the binary builds enough Microsoft
reputation, or until it's signed with a code-signing certificate.

A free OSS signing cert via SignPath/Certum is being applied for — once
approved, builds from v1.1+ will be signed and SmartScreen will trust them
automatically.

## Where data is stored

`%APPDATA%\EmailForwarder\` — contains:
- `collector.db` (SQLite settings + activity log)
- `secret.key` (Fernet key for encrypted IMAP/OAuth secrets — back this up!)
- `eml/YYYY/MM/*.eml` (local archive of every received message)

To uninstall completely: delete the .exe + that folder.
