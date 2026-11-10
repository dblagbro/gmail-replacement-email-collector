"""Provider-free regressions for the dependency and authentication upgrade."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from app import auth, crypto, db, gmail_client, main, oauth_state

ORIGIN = "https://collector.test"
PREFIX = "/email-collector"
SYNTHETIC_PASSWORD = "collector synthetic fixture"

@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    db.init_db()
    with db.conn() as c:
        for table in ("messages", "rules", "accounts", "oauth", "activity", "settings_kv"):
            c.execute(f"DELETE FROM {table}")
    # Keep tests fast without changing production bcrypt cost.
    original = auth.bcrypt.gensalt
    monkeypatch.setattr(auth.bcrypt, "gensalt", lambda: original(rounds=4))
    monkeypatch.setattr(main.forwarder, "reconcile", MagicMock())
    monkeypatch.setattr(main.forwarder, "restart_account", MagicMock())
    monkeypatch.setattr(main.forwarder, "stop_all", MagicMock())
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/network access forbidden in tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)

def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
        base_url=ORIGIN + PREFIX + "/", headers={"Origin": ORIGIN}, follow_redirects=False)

def run(test):
    return asyncio.run(test())

def test_setup_login_templates_and_cookie():
    async def check():
        async with client() as c:
            assert (await c.get("setup")).status_code == 200
            assert (await c.get("health")).json()["version"] == "1.1.0"
            response = await c.post("setup", data={"password": SYNTHETIC_PASSWORD, "confirm": SYNTHETIC_PASSWORD})
            assert response.status_code == 303
            cookie = response.headers["set-cookie"]
            for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Path=/email-collector", "Max-Age=86400"):
                assert attribute in cookie
            for route in ("", "accounts/new", "settings", "archive", "oauth", "rules"):
                response = await c.get(route)
                assert response.status_code == 200, (route, response.status_code)
                assert "/email-collector/static/" in response.text
            assert (await c.get("logout")).status_code == 303
            assert (await c.get("")).status_code == 307
            assert (await c.get("login")).status_code == 200
            assert "Bad password" in (await c.post("login", data={"password": "invalid synthetic value"})).text
            assert (await c.post("login", data={"password": SYNTHETIC_PASSWORD})).status_code == 303
    run(check)

@pytest.mark.parametrize("route", ["", "accounts/new", "settings", "archive", "archive/1", "archive/1/download", "oauth", "rules", "oauth/callback?code=synthetic"])
def test_anonymous_routes_rejected(route):
    auth.set_password(SYNTHETIC_PASSWORD)
    async def check():
        async with client() as c:
            r = await c.get(route)
            assert r.status_code == 307
            assert r.headers["location"] == PREFIX + "/login"
    run(check)

@pytest.mark.parametrize("origin", ["https://untrusted.invalid", "null", "https://collector.test.untrusted.invalid", "https://[invalid", ""])
def test_cross_origin_and_missing_origin_cannot_mutate(origin):
    async def check():
        async with client() as c:
            c.headers.pop("Origin")
            if origin:
                c.headers["Origin"] = origin
            assert (await c.post("setup", data={"password": SYNTHETIC_PASSWORD, "confirm": SYNTHETIC_PASSWORD})).status_code == 403
            assert not auth.is_setup()
    run(check)

def test_referer_fallback_and_invalid_origin_not_overridden():
    async def check():
        async with client() as c:
            c.headers.pop("Origin")
            c.headers["Referer"] = ORIGIN + PREFIX + "/setup"
            assert (await c.post("setup", data={"password": SYNTHETIC_PASSWORD, "confirm": SYNTHETIC_PASSWORD})).status_code == 303
            c.headers["Origin"] = "null"
            assert (await c.post("settings", data={"retention_days": "9"})).status_code == 403
    run(check)

def test_sessions_expire_revoke_and_invalidate_legacy_and_password_change(monkeypatch):
    auth.set_password(SYNTHETIC_PASSWORD)
    token = auth.new_session_token()
    assert auth.is_session_valid(token)
    assert db.get_setting("session:" + token) is None
    db.set_setting("session:legacy-synthetic", "1")
    assert not auth.is_session_valid("legacy-synthetic")
    assert not auth.is_session_valid("x" * 257)
    saved = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: saved + 86401)
    assert not auth.is_session_valid(token)
    token = auth.new_session_token()
    auth.revoke_session(token)
    assert not auth.is_session_valid(token)
    token = auth.new_session_token()
    auth.set_password("changed synthetic fixture")
    assert not auth.is_session_valid(token)

def test_password_byte_limit_and_unicode():
    auth.set_password(SYNTHETIC_PASSWORD)
    assert not auth.verify_password("x" * 73)
    with pytest.raises(ValueError):
        auth.set_password("é" * 37)

def test_authenticated_forms_and_archive_are_compatible():
    async def check():
        async with client() as c:
            await c.post("setup", data={"password": SYNTHETIC_PASSWORD, "confirm": SYNTHETIC_PASSWORD})
            r = await c.post("accounts/save", data={"name": "Synthetic fixture", "imap_host": "mail.invalid", "imap_username": "fixture", "imap_password": "synthetic mailbox value", "destination_gmail": "fixture@example.invalid", "enabled": "0"})
            assert r.status_code == 303
            a = db.list_accounts()[0]
            assert crypto.decrypt(a["imap_password_enc"]) == "synthetic mailbox value"
            assert (await c.get(f"accounts/{a['id']}/edit")).status_code == 200
            assert (await c.post("settings", data={"retention_days": "12", "default_label": "fixture"})).status_code == 303
            assert db.get_setting("retention_days") == "12"
            assert (await c.post("rules/save", data={"name": "fixture", "match_pattern": "*@example.invalid"})).status_code == 303
            assert (await c.get("rules")).status_code == 200
            from app.paths import EML_DIR
            EML_DIR.mkdir(parents=True, exist_ok=True)
            message = EML_DIR / "synthetic.eml"
            message.write_bytes(b"Subject: <script>synthetic</script>\r\n\r\nFixture")
            with db.conn() as conn:
                mid = conn.execute("INSERT INTO messages(account_id,message_id,subject,status,eml_path,inserted_at) VALUES(?,?,?,?,?,?)", (a["id"], "synthetic-message", "<script>synthetic</script>", "inserted", str(message), "2026-11-10T00:00:00+00:00")).lastrowid
            r = await c.get(f"archive/{mid}")
            assert r.status_code == 200 and "&lt;script&gt;" in r.text and "<script>synthetic" not in r.text
            assert (await c.get(f"archive/{mid}/download")).content == message.read_bytes()
    run(check)

def test_oauth_state_binding_expiry_and_atomic_replay(monkeypatch):
    auth.set_password(SYNTHETIC_PASSWORD)
    session, other = auth.new_session_token(), auth.new_session_token()
    redirect = ORIGIN + PREFIX + "/oauth/callback"
    oauth_state.remember("synthetic-state", session, "synthetic-pending", "synthetic-verifier", redirect)
    for state, user, target in [(None, session, redirect), ("wrong", session, redirect), ("synthetic-state", other, redirect), ("synthetic-state", session, "https://wrong.invalid")]:
        with pytest.raises(oauth_state.InvalidOAuthState):
            oauth_state.consume(state, user, target)
    def consume():
        try:
            oauth_state.consume("synthetic-state", session, redirect)
            return True
        except oauth_state.InvalidOAuthState:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: consume(), range(4))).count(True) == 1
    oauth_state.remember("expired-state", session, "pending", "verifier", redirect)
    now = time.time()
    monkeypatch.setattr(oauth_state.time, "time", lambda: now + 601)
    with pytest.raises(oauth_state.InvalidOAuthState):
        oauth_state.consume("expired-state", session, redirect)

def test_oauth_uses_saved_pkce_and_distinct_pending_records(monkeypatch):
    auth.set_password(SYNTHETIC_PASSWORD)
    session = auth.new_session_token()
    redirect = ORIGIN + PREFIX + "/oauth/callback"
    monkeypatch.setattr(gmail_client, "BUILTIN_OAUTH_CLIENT_ID", "synthetic-client")
    monkeypatch.setattr(gmail_client, "BUILTIN_OAUTH_CLIENT_SECRET", "synthetic-secret")
    created = []
    def fake_flow(config, **kwargs):
        flow = MagicMock()
        flow.code_verifier = "synthetic-code-verifier"
        flow.authorization_url.return_value = ("https://accounts.google.com/fixture", "state-" + str(len(created)))
        flow.credentials = SimpleNamespace(refresh_token="synthetic-refresh", token="synthetic-access", expiry=None, scopes=["fixture-scope"])
        created.append((kwargs, flow))
        return flow
    monkeypatch.setattr(gmail_client.Flow, "from_client_config", fake_flow)
    service = MagicMock()
    service.users().getProfile().execute.return_value = {"emailAddress": "fixture@example.invalid"}
    monkeypatch.setattr(gmail_client, "build", lambda *a, **k: service)
    _, state1 = gmail_client.begin_flow(redirect, session_token=session)
    _, state2 = gmail_client.begin_flow(redirect, session_token=session)
    assert state1 != state2
    assert created[0][0]["autogenerate_code_verifier"] is True
    assert len(db.list_oauth_accounts()) == 2
    result = gmail_client.complete_flow("synthetic-code", redirect, state=state1, session_token=session)
    assert result == "fixture@example.invalid"
    assert created[-1][0]["state"] == state1
    assert created[-1][0]["code_verifier"] == "synthetic-code-verifier"
    created[-1][1].fetch_token.assert_called_once_with(code="synthetic-code")
    assert crypto.decrypt(db.get_oauth(result)["refresh_token_enc"]) == "synthetic-refresh"
    with pytest.raises(oauth_state.InvalidOAuthState):
        gmail_client.complete_flow("synthetic-code", redirect, state=state1, session_token=session)

def test_oauth_multipart_and_callback_reject_missing_state(monkeypatch):
    auth.set_password(SYNTHETIC_PASSWORD)
    observed = []
    def begin(**kwargs):
        observed.append(kwargs)
        return "https://accounts.google.com/fixture", "synthetic-state"
    monkeypatch.setattr(gmail_client, "begin_flow", begin)
    async def check():
        async with client() as c:
            await c.post("login", data={"password": SYNTHETIC_PASSWORD})
            response = await c.post("oauth/start", data={"mode": "byo"}, files={"client_secret_json": ("fixture.json", b'{"web":{"client_id":"synthetic","client_secret":"fixture"}}', "application/json")})
            assert response.status_code == 303
            assert auth.is_session_valid(observed[0]["session_token"])
            assert observed[0]["redirect_uri"] == ORIGIN + PREFIX + "/oauth/callback"
            assert (await c.get("oauth/callback?code=synthetic")).status_code == 400
    run(check)

def test_lifespan_preserves_worker_and_scheduler_lifecycle(monkeypatch):
    scheduler = MagicMock()
    monkeypatch.setattr(main, "scheduler", scheduler)
    async def check():
        async with main.lifespan(main.app):
            main.forwarder.reconcile.assert_called_once()
            scheduler.start.assert_called_once()
        main.forwarder.stop_all.assert_called_once()
        scheduler.shutdown.assert_called_once()
    run(check)
