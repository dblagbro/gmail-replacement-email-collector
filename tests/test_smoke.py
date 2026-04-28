"""Smoke tests — make sure the app boots and core modules import cleanly."""
import os
import sys
import tempfile

# Use a throwaway data dir so the test doesn't touch a real install
os.environ["EMAIL_FORWARDER_DATA_DIR"] = tempfile.mkdtemp(prefix="ef-test-")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_imports():
    from app import db, archive, crypto, rules, gmail_client, imap_worker, forwarder, auth
    assert db.SCHEMA
    assert archive.archive_until is not None


def test_db_init_idempotent():
    from app import db
    db.init_db()
    db.init_db()  # second call should be a no-op
    db.set_setting("foo", "bar")
    assert db.get_setting("foo") == "bar"


def test_crypto_roundtrip():
    from app import crypto
    plain = "Super*120120"
    enc = crypto.encrypt(plain)
    assert enc != plain
    assert crypto.decrypt(enc) == plain
    assert crypto.encrypt(None) is None
    assert crypto.decrypt(None) is None


def test_rules_glob():
    from app.rules import _match
    assert _match("user@spam.com", "*@spam.com")
    assert _match("foo@bar.com", "re:^foo@")
    assert not _match("foo@bar.com", "*@spam.com")
