"""Run only inside an isolated container on a private restored copy.

The orchestrator must provide --network none and this script, never production
data. Provider workers and scheduled destructive/notification tasks are disabled.
Only counts and booleans leave the container; no mail or credentials are printed.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

assert os.environ.get("COLLECTOR_RECOVERY_PROBE") == "private-copy-only"
assert Path('/data/.recovery-copy').exists()
sys.path.insert(0, '/app')
from app import crypto, db, main

def fingerprint():
    c=sqlite3.connect('file:/data/collector.db?mode=ro',uri=True)
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    result={}
    for table in ['accounts','messages','settings_kv','rules','oauth']:
        rows=c.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
        result[table]={'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
    c.close();return result

def encrypted_count():
    count=0
    with db.conn() as c:
        for table,fields in [('accounts',['imap_password_enc']),('oauth',['client_id_enc','client_secret_enc','refresh_token_enc','access_token_enc'])]:
            for row in c.execute('SELECT '+','.join(fields)+' FROM '+table):
                for value in row:
                    if value:
                        assert isinstance(crypto.decrypt(value),str);count+=1
    return count

if len(sys.argv)>1 and sys.argv[1]=='serve':
    class NoScheduler:
        def add_job(self,*a,**k):pass
        def start(self):pass
        def shutdown(self,*a,**k):pass
    main.forwarder.reconcile=lambda:None
    main.forwarder.stop_all=lambda:None
    main.scheduler=NoScheduler()
    import uvicorn
    uvicorn.run(main.app,host='127.0.0.1',port=8077,log_level='critical',access_log=False)
else:
    before=fingerprint();keyhash=hashlib.sha256(Path('/data/secret.key').read_bytes()).hexdigest()
    enc=encrypted_count();checks=[]
    process=subprocess.Popen([sys.executable,__file__,'serve'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if process.poll() is not None:raise RuntimeError('isolated server exited')
            try:
                result=json.load(urllib.request.urlopen('http://127.0.0.1:8077/health',timeout=2));break
            except (urllib.error.URLError,TimeoutError):time.sleep(0.5)
        else:raise RuntimeError('isolated health timed out')
        assert result['status']=='ok';checks.append('health')
        # Disable automatic redirects; a redirect to login is the required result.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a,**k):return None
        opener=urllib.request.build_opener(NoRedirect)
        for path,expected in [('/login',200),('/',307),('/settings',307),('/oauth',307),('/archive',307)]:
            try:response=opener.open('http://127.0.0.1:8077'+path,timeout=3);status=response.status;response.close()
            except urllib.error.HTTPError as e:status=e.code;e.close()
            assert status==expected,(path,status);checks.append(path)
    finally:
        process.terminate()
        try:process.wait(15)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    assert fingerprint()==before
    assert hashlib.sha256(Path('/data/secret.key').read_bytes()).hexdigest()==keyhash
    assert encrypted_count()==enc
    print(json.dumps({'ok':True,'version':result['version'],'checks':checks,'protected_tables_unchanged':True,'encrypted_values_readable':enc,'key_unchanged':True,'provider_workers_disabled':True,'scheduled_jobs_disabled':True}))
