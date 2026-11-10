"""Scoped collector recovery and release operator. Run through the capacity guard.

All private evidence and snapshots stay in a root-only backup directory. The
receipt contains only hashes, counts, health results and container image IDs.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,sqlite3,subprocess,time

SERVICE='gmail-email-collector'
def patch_image(text,old,new):
    pattern=r'(?ms)(^  '+re.escape(SERVICE)+r':\n)(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)'
    matches=list(re.finditer(pattern,text));assert len(matches)==1,'Expected exactly one collector service'
    match=matches[0];body=match[2]
    expected=r'(?m)^    image: '+re.escape(old)+r'[ \t]*$'
    updated,n=re.subn(expected,'    image: '+new,body);assert n==1,'Unexpected image line'
    return text[:match.start(2)]+updated+text[match.end(2):]

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def inspect(name):return json.loads(subprocess.check_output(['docker','inspect',name]))[0]
def all_containers():
    ids=subprocess.check_output(['docker','ps','-aq'],text=True).split()
    return {x['Name'].lstrip('/'):{'id':x['Id'],'image':x['Image'],'state':x['State']['Status']} for x in json.loads(subprocess.check_output(['docker','inspect',*ids])) if x['Name'].lstrip('/')!=SERVICE}
def spec(x):
    config={k:v for k,v in x['Config'].items() if k not in ['Image','Labels','Hostname','Env']}
    base_keys={'PATH','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256'}
    config['Env']={k:v for k,v in (e.split('=',1) for e in x['Config']['Env']) if k not in base_keys}
    host={k:v for k,v in x['HostConfig'].items() if k not in ['ContainerIDFile']}
    # Docker serializes inherited default DNS as either null or an empty list.
    # Nonempty explicit DNS configuration must still compare exactly.
    for key in ['Dns','DnsOptions','DnsSearch']:
        if host.get(key) is None:host[key]=[]
    return {'config':config,'host':host,'mounts':[{k:v for k,v in m.items() if k not in ['Name']} for m in x['Mounts']]}
def manifest(path):
    result={}
    for p in sorted(Path(path).rglob('*')):
        assert not p.is_symlink(),'Unexpected data symlink'
        if p.is_file():result[str(p.relative_to(path))]=digest(p)
    return result
def protected(path):
    c=sqlite3.connect('file:'+str(Path(path)/'collector.db')+'?mode=ro',uri=True)
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    result={}
    for table in ['accounts','messages','settings_kv','rules','oauth']:
        rows=c.execute('SELECT * FROM "'+table+'" ORDER BY rowid').fetchall()
        result[table]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
    c.close();return result
def health(image):
    for _ in range(40):
        x=inspect(SERVICE)
        if x['State']['Status']=='running' and x['State'].get('Health',{}).get('Status')=='healthy':
            assert x['Image']==image
            return {'status':'healthy','image':image,'restart_count':x['RestartCount']}
        time.sleep(3)
    raise RuntimeError('Collector health timeout')
def nginx_hash():
    result={}
    for p in sorted(Path('/etc/nginx').rglob('*')):
        if p.is_file():result[str(p)]=digest(p)
    return hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['rehearse','deploy']);parser.add_argument('--compose',required=True);parser.add_argument('--data',required=True);parser.add_argument('--backup-root',required=True);parser.add_argument('--receipt',required=True);parser.add_argument('--original-image',required=True);parser.add_argument('--candidate-image',required=True);parser.add_argument('--probe',required=True);parser.add_argument('--recovery-receipt');parser.add_argument('--approval');args=parser.parse_args()
    assert os.geteuid()==0
    assert b'capacity_guard.py' in Path('/proc/'+str(os.getppid())+'/cmdline').read_bytes()
    os.umask(0o077)
    receipt=Path(args.receipt);assert not receipt.exists()
    compose=Path(args.compose);data=Path(args.data);root=Path(args.backup_root);root.mkdir(parents=True,exist_ok=True);os.chmod(root,0o700)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=root/(args.action+'-'+stamp);backup.mkdir(mode=0o700)
    state={'action':args.action,'pid':os.getpid(),'deployed':False,'backup':str(backup),'original_image':args.original_image,'candidate_image':args.candidate_image}
    def save(phase):
        state.update(phase=phase,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());p=receipt.with_suffix('.tmp');p.write_text(json.dumps(state,indent=2)+'\n');p.replace(receipt)
    def command(argv):return subprocess.run(argv,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    original=inspect(SERVICE);assert original['Image']==args.original_image and original['State']['Status']=='running'
    assert original['State'].get('Health',{}).get('Status')=='healthy'
    assert [m['Source'] for m in original['Mounts'] if m['Destination']=='/data']==[str(data)]
    candidate=json.loads(subprocess.check_output(['docker','image','inspect',args.candidate_image]))[0];assert candidate['Id']==args.candidate_image
    before=compose.read_text();before_hash=digest(compose);others=all_containers();nginx=nginx_hash()
    (backup/'container-private.json').write_text(json.dumps(original))
    shutil.copy2(compose,backup/'compose-original.yml')
    if (compose.parent/'.env').exists():shutil.copy2(compose.parent/'.env',backup/'env-private')
    state['compose_before_sha256']=before_hash
    env={e.split('=',1)[0]:e.split('=',1)[1] for e in original['Config']['Env']}
    if args.action=='deploy':
        recovery=json.loads(Path(args.recovery_receipt).read_text());approval=json.loads(Path(args.approval).read_text())
        assert recovery['phase']=='rehearsed' and recovery['candidate_image']==args.candidate_image
        assert approval['merged'] and approval['checks_passed'] and approval['candidate_inputs_equal_merged_source'] and approval['image_id']==args.candidate_image
        changed=patch_image(before,original['Config']['Image'],args.candidate_image)
        # Compose parsing is private; require that only this service image changes.
        tmp=compose.parent/('.gmail-candidate-'+stamp+'.yml');tmp.write_text(changed)
        try:
            oldcfg=json.loads(subprocess.check_output(['docker','compose','-f',str(compose),'config','--format','json'],stderr=subprocess.DEVNULL))
            newcfg=json.loads(subprocess.check_output(['docker','compose','-f',str(tmp),'config','--format','json'],stderr=subprocess.DEVNULL))
            oldcfg['services'][SERVICE]['image']=args.candidate_image
            assert oldcfg==newcfg,'Compose change extends beyond collector image'
        finally:tmp.unlink()
    save('quiescing_for_consistent_snapshot');stopped=False;config_changed=False
    try:
        command(['docker','stop','--time','60',SERVICE]);stopped=True
        assert inspect(SERVICE)['State']['Status']=='exited'
        assert digest(compose)==before_hash and all_containers()==others
        snapshot=backup/'snapshot';shutil.copytree(data,snapshot)
        source_manifest=manifest(data);assert manifest(snapshot)==source_manifest
        state['snapshot_files']=len(source_manifest);state['snapshot_bytes']=sum(p.stat().st_size for p in snapshot.rglob('*') if p.is_file())
        state['snapshot_manifest_sha256']=hashlib.sha256(json.dumps(source_manifest,sort_keys=True).encode()).hexdigest()
        (backup/'manifest-private.json').write_text(json.dumps(source_manifest))
        tables=protected(snapshot);state['protected_table_counts']={k:v['count'] for k,v in tables.items()}
        assert protected(data)==tables
        # SQLite read-only WAL access can update ephemeral shared-memory files.
        # Normalize only the copied database, then hash that restore input.
        with sqlite3.connect(snapshot/'collector.db') as c:
            assert c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]==0
        c.close()
        assert protected(snapshot)==tables
        source_manifest=manifest(snapshot)
        state['normalized_snapshot_manifest_sha256']=hashlib.sha256(json.dumps(source_manifest,sort_keys=True).encode()).hexdigest()
        (backup/'normalized-manifest-private.json').write_text(json.dumps(source_manifest))
        if args.action=='rehearse':
            command(['docker','start',SERVICE]);stopped=False;health(args.original_image);save('rehearsing_private_restores')
            results=[]
            for index,image in enumerate([args.candidate_image,args.original_image]):
                restored=backup/('restore-'+str(index));shutil.copytree(snapshot,restored);assert manifest(restored)==source_manifest
                (restored/'.recovery-copy').write_text('isolated recovery copy\n')
                argv=['docker','run','--rm','--network','none','--read-only','--memory','1g','--cpus','2','--tmpfs','/tmp:rw,nosuid,nodev,size=128m','--mount','type=bind,src='+str(restored)+',dst=/data','--mount','type=bind,src='+str(Path(args.probe).resolve())+',dst=/restore_probe.py,readonly','-e','COLLECTOR_RECOVERY_PROBE=private-copy-only','-e','URL_PREFIX='+env.get('URL_PREFIX',''),'-e','PUBLIC_BASE_URL='+env.get('PUBLIC_BASE_URL',''),image,'python','/restore_probe.py']
                # Probe never emits private payloads; failed output is kept root-only.
                result=subprocess.run(argv,capture_output=True,text=True,timeout=180)
                (backup/('probe-'+str(index)+'.log')).write_text(result.stdout+'\n'+result.stderr)
                assert result.returncode==0,'Isolated restore probe failed; see private log'
                evidence=json.loads(result.stdout.strip().splitlines()[-1]);assert evidence['ok'];results.append(evidence)
            state['probes']=results;assert all_containers()==others and digest(compose)==before_hash and nginx_hash()==nginx
            state['original_health']=health(args.original_image);save('rehearsed')
        else:
            assert digest(compose)==before_hash and all_containers()==others and nginx_hash()==nginx
            # Atomic, same-directory replacement preserves all unrelated bytes.
            temp=compose.with_name(compose.name+'.gmail-update');temp.write_text(changed);shutil.copystat(compose,temp);temp.replace(compose);config_changed=True
            save('starting_candidate')
            command(['docker','compose','-f',str(compose),'up','-d','--no-deps','--pull','never',SERVICE]);stopped=False
            state['health']=health(args.candidate_image)
            deployed=inspect(SERVICE)
            (backup/'candidate-container-private.json').write_text(json.dumps(deployed))
            assert spec(deployed)==spec(original),'Runtime configuration changed beyond image'
            assert all_containers()==others and nginx_hash()==nginx
            # Workers resume normally; message/activity changes are legitimate.
            # Static configuration, rule/account identity and encryption key are checked.
            assert digest(data/'secret.key')==digest(snapshot/'secret.key')
            after=protected(data)
            for table in ['rules','settings_kv']:assert after[table]==tables[table]
            with sqlite3.connect(data/'collector.db') as c, sqlite3.connect(snapshot/'collector.db') as b:
                cols=[r[1] for r in c.execute('PRAGMA table_info(accounts)') if r[1] not in ['last_check_at','last_error']]
                query='SELECT '+','.join(cols)+' FROM accounts ORDER BY id';assert c.execute(query).fetchall()==b.execute(query).fetchall()
            state.update(deployed=True,compose_after_sha256=digest(compose),unrelated_containers_unchanged=True,nginx_unchanged=True,key_unchanged=True,configuration_preserved=True);save('deployed_verified')
    except BaseException as error:
        state['error_class']=type(error).__name__
        if config_changed:
            # No schema migration is introduced. Preserve new mail and refreshed tokens.
            expected=hashlib.sha256(changed.encode()).hexdigest()
            assert digest(compose)==expected,'Concurrent Compose edit; refuse overwrite'
            temp=compose.with_name(compose.name+'.gmail-rollback');shutil.copy2(backup/'compose-original.yml',temp);temp.replace(compose)
            command(['docker','compose','-f',str(compose),'up','-d','--no-deps','--pull','never',SERVICE]);stopped=False
        elif stopped:
            command(['docker','start',SERVICE]);stopped=False
        state['original_health']=health(args.original_image);save('failed_original_restored');raise
    print(json.dumps({k:state[k] for k in ['phase','deployed','original_image','candidate_image']}))

if __name__=='__main__':main()
