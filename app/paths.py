"""Platform-aware data paths.

Resolves the data directory once at import time. Order of precedence:
  1. EMAIL_FORWARDER_DATA_DIR env var (Docker compose mounts /data here)
  2. %APPDATA%/EmailForwarder on Windows
  3. ~/.local/share/email-forwarder on Linux/macOS
"""
from __future__ import annotations
import os
import sys
from pathlib import Path


def _resolve_data_dir() -> Path:
    env = os.environ.get("EMAIL_FORWARDER_DATA_DIR")
    if env:
        return Path(env)
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "EmailForwarder"
    return Path.home() / ".local" / "share" / "email-forwarder"


DATA_DIR: Path = _resolve_data_dir()
DB_PATH: Path = DATA_DIR / "collector.db"
SECRET_KEY_PATH: Path = DATA_DIR / "secret.key"
EML_DIR: Path = DATA_DIR / "eml"
ATTACH_DIR: Path = DATA_DIR / "attachments"
LOG_DIR: Path = DATA_DIR / "logs"


def ensure_dirs() -> None:
    for p in (DATA_DIR, EML_DIR, ATTACH_DIR, LOG_DIR):
        p.mkdir(parents=True, exist_ok=True)
