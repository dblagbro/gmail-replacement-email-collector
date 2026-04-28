"""Worker orchestrator: spawns one AccountWorker thread per enabled account.

The main process keeps a registry; the UI calls reconcile() whenever an
account is added/edited/enabled/disabled so the workers stay in sync without
restarting the container.
"""
from __future__ import annotations
import logging
import threading
from typing import Dict

from app import db
from app.imap_worker import AccountWorker

logger = logging.getLogger(__name__)

_workers: Dict[int, AccountWorker] = {}
_lock = threading.Lock()


def reconcile() -> None:
    """Bring running workers in line with the DB state."""
    with _lock:
        accounts = {a["id"]: a for a in db.list_accounts()}
        # Stop workers for removed/disabled accounts
        for aid in list(_workers.keys()):
            a = accounts.get(aid)
            if a is None or not a["enabled"]:
                logger.info("Stopping worker for account %s", aid)
                _workers[aid].stop()
                del _workers[aid]
        # Start workers for newly enabled accounts
        for aid, a in accounts.items():
            if a["enabled"] and aid not in _workers:
                logger.info("Starting worker for account %s (%s)", aid, a["name"])
                w = AccountWorker(aid)
                w.start()
                _workers[aid] = w


def restart_account(account_id: int) -> None:
    with _lock:
        w = _workers.pop(account_id, None)
        if w:
            w.stop()
    reconcile()


def stop_all() -> None:
    with _lock:
        for w in _workers.values():
            w.stop()
        _workers.clear()


def status() -> dict[int, str]:
    with _lock:
        return {aid: ("running" if w.is_alive() else "stopped") for aid, w in _workers.items()}
