"""FastAPI entrypoint — UI routes, OAuth wizard, lifecycle."""
from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import archive, auth, db, forwarder, gmail_client
from app.config import (
    DEFAULT_LABEL,
    DEFAULT_RETENTION_DAYS,
    SWEEP_INTERVAL_HOURS,
    URL_PREFIX,
)
from app.crypto import encrypt
from app.paths import ensure_dirs

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    db.init_db()
    # Seed defaults if missing
    if db.get_setting("retention_days") is None:
        db.set_setting("retention_days", str(DEFAULT_RETENTION_DAYS))
    if db.get_setting("default_label") is None:
        db.set_setting("default_label", DEFAULT_LABEL)
    forwarder.reconcile()
    scheduler.add_job(archive.sweep_expired, "interval", hours=SWEEP_INTERVAL_HOURS, id="sweep")
    scheduler.start()
    db.log_activity("info", "Service started")
    try:
        yield
    finally:
        forwarder.stop_all()
        scheduler.shutdown(wait=False)


app = FastAPI(title="Gmail Replacement Email Collector", root_path=URL_PREFIX, lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")


# ---- helpers ----

def _ctx(request: Request, **extra) -> dict:
    base = {"request": request, "url_prefix": URL_PREFIX, "now": datetime.now(timezone.utc)}
    base.update(extra)
    return base


def _require_auth(request: Request, ef_session: str | None = Cookie(None)) -> str:
    if not auth.is_setup():
        # Bootstrap: redirect to setup page
        raise HTTPException(status_code=307, headers={"Location": f"{URL_PREFIX}/setup"})
    if not auth.is_session_valid(ef_session):
        raise HTTPException(status_code=307, headers={"Location": f"{URL_PREFIX}/login"})
    return ef_session  # type: ignore[return-value]


# ---- health ----

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ---- setup (first run) ----

@app.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request):
    if auth.is_setup():
        return RedirectResponse(f"{URL_PREFIX}/login", status_code=303)
    return templates.TemplateResponse("setup.html", _ctx(request))


@app.post("/setup")
def setup_post(request: Request, password: str = Form(...), confirm: str = Form(...)):
    if auth.is_setup():
        return RedirectResponse(f"{URL_PREFIX}/login", status_code=303)
    if password != confirm or len(password) < 8:
        return templates.TemplateResponse("setup.html", _ctx(request, error="Passwords must match and be 8+ chars"))
    auth.set_password(password)
    tok = auth.new_session_token()
    resp = RedirectResponse(f"{URL_PREFIX}/", status_code=303)
    resp.set_cookie("ef_session", tok, httponly=True, samesite="lax", max_age=86400)
    return resp


# ---- login ----

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if not auth.is_setup():
        return RedirectResponse(f"{URL_PREFIX}/setup", status_code=303)
    return templates.TemplateResponse("login.html", _ctx(request))


@app.post("/login")
def login_post(request: Request, password: str = Form(...)):
    if not auth.verify_password(password):
        return templates.TemplateResponse("login.html", _ctx(request, error="Bad password"))
    tok = auth.new_session_token()
    resp = RedirectResponse(f"{URL_PREFIX}/", status_code=303)
    resp.set_cookie("ef_session", tok, httponly=True, samesite="lax", max_age=86400)
    return resp


@app.get("/logout")
def logout(ef_session: str | None = Cookie(None)):
    if ef_session:
        auth.revoke_session(ef_session)
    resp = RedirectResponse(f"{URL_PREFIX}/login", status_code=303)
    resp.delete_cookie("ef_session")
    return resp


# ---- dashboard ----

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _=Depends(_require_auth)):
    return templates.TemplateResponse("dashboard.html", _ctx(
        request,
        accounts=db.list_accounts(),
        oauth_accounts=db.list_oauth_accounts(),
        stats=db.stats(),
        worker_status=forwarder.status(),
        activity=db.recent_activity(50),
    ))


# ---- accounts ----

@app.get("/accounts/new", response_class=HTMLResponse)
def account_new(request: Request, _=Depends(_require_auth)):
    return templates.TemplateResponse("account_form.html", _ctx(
        request, account=None, oauth_accounts=db.list_oauth_accounts(),
    ))


@app.get("/accounts/{aid}/edit", response_class=HTMLResponse)
def account_edit(request: Request, aid: int, _=Depends(_require_auth)):
    a = db.get_account(aid)
    if a is None:
        raise HTTPException(404)
    return templates.TemplateResponse("account_form.html", _ctx(
        request, account=a, oauth_accounts=db.list_oauth_accounts(),
    ))


@app.post("/accounts/save")
def account_save(
    request: Request,
    _=Depends(_require_auth),
    account_id: int = Form(0),
    name: str = Form(...),
    imap_host: str = Form(...),
    imap_port: int = Form(993),
    imap_username: str = Form(...),
    imap_password: str = Form(""),
    imap_folder: str = Form("INBOX"),
    use_ssl: int = Form(1),
    poll_mode: str = Form("idle"),
    poll_interval_sec: int = Form(300),
    gmail_label: str = Form(""),
    destination_gmail: str = Form(...),
    post_fetch_action: str = Form("keep"),
    enabled: int = Form(1),
):
    if post_fetch_action not in ("keep", "delete"):
        post_fetch_action = "keep"
    fields = dict(
        name=name, imap_host=imap_host, imap_port=imap_port,
        imap_username=imap_username, imap_folder=imap_folder, use_ssl=use_ssl,
        poll_mode=poll_mode, poll_interval_sec=poll_interval_sec,
        gmail_label=gmail_label or None, destination_gmail=destination_gmail,
        post_fetch_action=post_fetch_action,
        enabled=enabled,
    )
    if imap_password:
        fields["imap_password_enc"] = encrypt(imap_password)
    if account_id:
        db.update_account(account_id, **fields)
    else:
        if not imap_password:
            raise HTTPException(400, "IMAP password required for new account")
        fields["imap_password_enc"] = encrypt(imap_password)
        account_id = db.create_account(**fields)
    forwarder.restart_account(account_id)
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)


@app.post("/accounts/{aid}/delete")
def account_delete(aid: int, _=Depends(_require_auth)):
    db.delete_account(aid)
    forwarder.reconcile()
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)


@app.post("/accounts/{aid}/toggle")
def account_toggle(aid: int, _=Depends(_require_auth)):
    a = db.get_account(aid)
    if a is None:
        raise HTTPException(404)
    db.update_account(aid, enabled=0 if a["enabled"] else 1)
    forwarder.reconcile()
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)


# ---- settings ----

@app.get("/settings", response_class=HTMLResponse)
def settings_get(request: Request, _=Depends(_require_auth)):
    return templates.TemplateResponse("settings.html", _ctx(
        request, settings=db.all_settings(),
    ))


@app.post("/settings")
def settings_post(
    request: Request,
    _=Depends(_require_auth),
    retention_days: int = Form(...),
    default_label: str = Form(""),
):
    db.set_setting("retention_days", str(max(1, retention_days)))
    db.set_setting("default_label", default_label)
    return RedirectResponse(f"{URL_PREFIX}/settings", status_code=303)


@app.post("/settings/password")
def settings_password(
    request: Request,
    _=Depends(_require_auth),
    current: str = Form(...),
    new: str = Form(...),
    confirm: str = Form(...),
):
    if not auth.verify_password(current):
        return templates.TemplateResponse("settings.html", _ctx(
            request, settings=db.all_settings(), pw_error="Current password incorrect",
        ))
    if new != confirm or len(new) < 8:
        return templates.TemplateResponse("settings.html", _ctx(
            request, settings=db.all_settings(), pw_error="New passwords must match and be 8+ chars",
        ))
    auth.set_password(new)
    return RedirectResponse(f"{URL_PREFIX}/settings", status_code=303)


# ---- archive ----

@app.get("/archive", response_class=HTMLResponse)
def archive_list(request: Request, _=Depends(_require_auth),
                 q: str | None = None, account_id: int | None = None,
                 page: int = 1):
    page = max(1, page)
    per = 50
    msgs = db.list_messages(account_id=account_id, limit=per, offset=(page - 1) * per, search=q)
    return templates.TemplateResponse("archive.html", _ctx(
        request, messages=msgs, accounts=db.list_accounts(),
        q=q or "", account_id=account_id, page=page, per=per,
    ))


@app.get("/archive/{mid}", response_class=HTMLResponse)
def archive_view(request: Request, mid: int, _=Depends(_require_auth)):
    m = db.get_message(mid)
    if m is None:
        raise HTTPException(404)
    raw_excerpt = ""
    if m["eml_path"] and Path(m["eml_path"]).exists():
        try:
            raw_excerpt = Path(m["eml_path"]).read_text(errors="replace")[:50000]
        except Exception as e:
            raw_excerpt = f"(error reading file: {e})"
    return templates.TemplateResponse("message.html", _ctx(
        request, m=m, raw_excerpt=raw_excerpt,
    ))


@app.get("/archive/{mid}/download")
def archive_download(mid: int, _=Depends(_require_auth)):
    m = db.get_message(mid)
    if m is None or not m["eml_path"] or not Path(m["eml_path"]).exists():
        raise HTTPException(404)
    return FileResponse(m["eml_path"], media_type="message/rfc822",
                        filename=f"message-{mid}.eml")


@app.post("/archive/{mid}/delete")
def archive_delete(mid: int, also_gmail: int = Form(0), _=Depends(_require_auth)):
    m = db.get_message(mid)
    if m is None:
        raise HTTPException(404)
    if also_gmail and m["gmail_msg_id"]:
        a = db.get_account(m["account_id"])
        if a and a["destination_gmail"]:
            try:
                gmail_client.trash_message(a["destination_gmail"], m["gmail_msg_id"])
            except Exception as e:
                logger.warning("Trash from Gmail failed: %s", e)
    eml = db.delete_message(mid)
    if eml:
        try:
            Path(eml).unlink(missing_ok=True)
        except OSError:
            pass
    return RedirectResponse(f"{URL_PREFIX}/archive", status_code=303)


# ---- OAuth wizard ----

@app.get("/oauth", response_class=HTMLResponse)
def oauth_index(request: Request, _=Depends(_require_auth)):
    return templates.TemplateResponse("oauth.html", _ctx(
        request, oauth_accounts=db.list_oauth_accounts(),
    ))


@app.post("/oauth/start")
def oauth_start(
    request: Request,
    _=Depends(_require_auth),
    mode: str = Form("builtin"),
    client_secret_json: UploadFile | None = File(None),
):
    redirect_uri = str(request.url_for("oauth_callback"))
    byo = None
    if mode == "byo":
        if not client_secret_json:
            raise HTTPException(400, "client_secret JSON file required for BYO mode")
        byo = (client_secret_json.file.read()).decode("utf-8")
    auth_url, _state = gmail_client.begin_flow(
        redirect_uri=redirect_uri,
        gmail_account="__pending__",
        use_builtin=(mode == "builtin"),
        byo_client_json=byo,
    )
    return RedirectResponse(auth_url, status_code=303)


@app.get("/oauth/callback")
def oauth_callback(request: Request, code: str | None = None, error: str | None = None):
    if error or not code:
        raise HTTPException(400, f"OAuth error: {error or 'no code'}")
    redirect_uri = str(request.url_for("oauth_callback"))
    email = gmail_client.complete_flow(code=code, redirect_uri=redirect_uri)
    db.log_activity("info", f"OAuth completed for {email}")
    return RedirectResponse(f"{URL_PREFIX}/oauth?ok={email}", status_code=303)


@app.post("/oauth/{account}/delete")
def oauth_delete(account: str, _=Depends(_require_auth)):
    db.delete_oauth(account)
    return RedirectResponse(f"{URL_PREFIX}/oauth", status_code=303)


# ---- rules ----

@app.get("/rules", response_class=HTMLResponse)
def rules_list(request: Request, _=Depends(_require_auth)):
    with db.conn() as c:
        rows = c.execute("SELECT r.*, a.name AS account_name FROM rules r "
                         "LEFT JOIN accounts a ON a.id=r.account_id ORDER BY r.id").fetchall()
    return templates.TemplateResponse("rules.html", _ctx(
        request, rules=rows, accounts=db.list_accounts(),
    ))


@app.post("/rules/save")
def rules_save(
    _=Depends(_require_auth),
    rule_id: int = Form(0),
    account_id: int | None = Form(None),
    name: str = Form(...),
    match_field: str = Form("from"),
    match_pattern: str = Form(...),
    action: str = Form("skip"),
    action_arg: str = Form(""),
    enabled: int = Form(1),
):
    fields = dict(
        account_id=account_id or None, name=name, match_field=match_field,
        match_pattern=match_pattern, action=action, action_arg=action_arg or None,
        enabled=enabled,
    )
    with db.conn() as c:
        if rule_id:
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE rules SET {sets} WHERE id=?", (*fields.values(), rule_id))
        else:
            cols = ", ".join(fields.keys())
            ph = ", ".join("?" * len(fields))
            c.execute(f"INSERT INTO rules({cols}) VALUES({ph})", tuple(fields.values()))
    return RedirectResponse(f"{URL_PREFIX}/rules", status_code=303)


@app.post("/rules/{rid}/delete")
def rules_delete(rid: int, _=Depends(_require_auth)):
    with db.conn() as c:
        c.execute("DELETE FROM rules WHERE id=?", (rid,))
    return RedirectResponse(f"{URL_PREFIX}/rules", status_code=303)


# ---- manual sweep / actions ----

@app.post("/actions/sweep")
def actions_sweep(_=Depends(_require_auth)):
    n = archive.sweep_expired()
    db.log_activity("info", f"Manual retention sweep: {n} purged")
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)


@app.post("/actions/reconcile")
def actions_reconcile(_=Depends(_require_auth)):
    forwarder.reconcile()
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)


def _do_manual_fetch(aid: int, include_seen: bool) -> None:
    """Run a one-off fetch in a background thread (so the HTTP request returns instantly).

    Initial import of years of mail can take minutes — never block the request handler.
    """
    from imap_tools import MailBox, MailBoxUnencrypted
    from app.crypto import decrypt
    from app.imap_worker import AccountWorker
    a = db.get_account(aid)
    if a is None:
        return
    pw = decrypt(a["imap_password_enc"]) or ""
    cls = MailBox if a["use_ssl"] else MailBoxUnencrypted
    worker = AccountWorker(aid)
    try:
        with cls(a["imap_host"], port=a["imap_port"]).login(
            a["imap_username"], pw, initial_folder=a["imap_folder"]
        ) as mb:
            if include_seen:
                seen_uids = mb.uids("SEEN")
                if seen_uids:
                    mb.flag(seen_uids, "\\Seen", False)
                    db.log_activity(
                        "info",
                        f"Manual fetch (include_seen): unflagged {len(seen_uids)} previously-read messages",
                        aid,
                    )
            db.log_activity("info", "Manual fetch started", aid)
            worker._process_unseen(mb, a)
            db.log_activity("info", "Manual fetch completed", aid)
        db.update_account_status(aid, None)
    except Exception as e:
        msg = f"Manual fetch failed: {e}"
        logger.exception(msg)
        db.log_activity("error", msg, aid)
        db.update_account_status(aid, msg)


@app.post("/accounts/{aid}/fetch")
def actions_fetch_now(aid: int, include_seen: int = Form(0), _=Depends(_require_auth)):
    """Kick off a manual fetch in the background; return immediately so the dashboard refreshes fast."""
    import threading
    if db.get_account(aid) is None:
        raise HTTPException(404)
    threading.Thread(
        target=_do_manual_fetch,
        args=(aid, bool(include_seen)),
        daemon=True,
        name=f"manual-fetch-{aid}",
    ).start()
    return RedirectResponse(f"{URL_PREFIX}/", status_code=303)
