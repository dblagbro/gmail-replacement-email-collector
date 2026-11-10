"""Boot the unmodified application on empty synthetic data, with no provider accounts."""
import json,os,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="collector-boot-") as directory:
    env=os.environ.copy()
    env.update(EMAIL_FORWARDER_DATA_DIR=directory,PUBLIC_BASE_URL="https://collector.test",URL_PREFIX="/email-collector",BUILTIN_OAUTH_CLIENT_ID="",BUILTIN_OAUTH_CLIENT_SECRET="")
    process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","18077","--log-level","critical","--no-access-log"],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if process.poll() is not None:raise RuntimeError("Unmodified application failed to start")
            try:
                health=json.load(urllib.request.urlopen("http://127.0.0.1:18077/health",timeout=1));break
            except (urllib.error.URLError,TimeoutError):time.sleep(0.25)
        else:raise RuntimeError("Application health timeout")
        assert health=={"status":"ok","version":"1.1.0"}
        with urllib.request.urlopen("http://127.0.0.1:18077/setup",timeout=2) as response:assert response.status==200
        import sqlite3
        with sqlite3.connect(Path(directory)/"collector.db") as db:
            assert db.execute("SELECT count(*) FROM accounts").fetchone()[0]==0
            assert db.execute("SELECT count(*) FROM oauth").fetchone()[0]==0
    finally:
        process.terminate()
        try:process.wait(10)
        except subprocess.TimeoutExpired:process.kill();process.wait();raise
    assert process.returncode==0
print(json.dumps({"unmodified_app_boot":True,"real_scheduler_start_stop":True,"synthetic_empty_database":True,"provider_accounts":0}))
