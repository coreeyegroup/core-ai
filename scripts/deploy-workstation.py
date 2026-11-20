"""Native deployment, rollback and local administration for CORE-AI only."""
import argparse
import base64
import datetime
import fnmatch
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ENV = Path('/etc/core-ai/workstation.env')
BASE = Path('/opt/core-ai')
SITE = Path('/etc/caddy/sites/core-ai.caddy')
CADDY = Path('/etc/caddy/Caddyfile')
PORT = 18787
PGPORT = 5434
ROLE = 'core_ai_app'
DATABASE = 'core_ai'
PSQL = '/usr/lib/postgresql/18/bin/psql'
MARKER = '# Managed by CORE-AI workstation\n'

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

def domain(value):
    if len(value)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',value):
        raise ValueError('Enter a DNS domain without scheme, port or path.')
    return value

def parse_env(path):
    return dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line and not line.startswith('#'))

def load_env():
    if ENV.is_symlink() or ENV.stat().st_uid!=0 or ENV.stat().st_mode & 0o077:
        raise ValueError('Workstation environment must be root-owned, mode 600 and not a symlink.')
    return parse_env(ENV)

def write_private(path,text):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
        f.write(text)
        temporary=f.name
    os.chmod(temporary,0o600)
    os.replace(temporary,path)

def pg(sql,password=None,database='postgres'):
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    env.update(PGCONNECT_TIMEOUT='5',PGPASSFILE='/dev/null')
    args=[PSQL,'-X','-w','-v','ON_ERROR_STOP=1','-A','-t','-p',str(PGPORT),'-d',database]
    if password is None:
        args=['runuser','-u','postgres','--',*args,'-h','/var/run/postgresql']
    else:
        env['PGPASSWORD']=password
        args+=['-h','127.0.0.1','-U',ROLE]
    result=subprocess.run(args,input=sql,text=True,capture_output=True,env=env,cwd='/tmp')
    if result.returncode:
        raise RuntimeError('CORE-AI PostgreSQL operation failed. Existing credentials were not reset; inspect the dedicated cluster.')
    return result.stdout.strip()

def database_setup(origin,model_url):
    clusters=run('pg_lsclusters','--no-header',capture_output=True,text=True).stdout.splitlines()
    own=[line.split() for line in clusters if line.split()[:2]==['18','core_ai']]
    if not own:
        for line in clusters:
            if line.split()[2]==str(PGPORT):
                raise ValueError('Port 5434 belongs to another PostgreSQL cluster.')
        with socket.socket() as s:
            s.bind(('127.0.0.1',PGPORT))
        run('pg_createcluster','18','core_ai','--port',str(PGPORT),'--start','--', '--auth-local=peer','--auth-host=scram-sha-256')
    subprocess.run(['pg_ctlcluster','18','core_ai','start'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    identity=pg("SELECT current_setting('server_version_num')::int/10000; SHOW data_directory; SHOW listen_addresses;").splitlines()
    if identity[:2]!=['18','/var/lib/postgresql/18/core_ai'] or identity[2] not in ('localhost','127.0.0.1'):
        raise ValueError('Unexpected CORE-AI cluster identity or non-loopback listener. No credentials changed.')
    role_exists=pg(f"SELECT count(*) FROM pg_roles WHERE rolname='{ROLE}'")=='1'
    owner=pg(f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{DATABASE}'")
    if owner and owner!=ROLE:
        raise ValueError('CORE-AI database has another owner.')
    if ENV.exists():
        cfg=load_env()
        from urllib.parse import urlsplit
        u=urlsplit(cfg['CORE_AI_DATABASE_URL'])
        if u.scheme!='postgresql' or u.hostname!='127.0.0.1' or u.port!=PGPORT or u.path!='/'+DATABASE or u.username!=ROLE or u.query or u.fragment or not re.fullmatch(r'[A-Za-z0-9_-]+',u.password or ''):
            raise ValueError('Environment does not match the dedicated CORE-AI database.')
        password=u.password
    else:
        if role_exists or owner:
            raise ValueError('Restore the existing CORE-AI environment file before installing. Passwords were not reset.')
        password=secrets.token_urlsafe(36)
        cfg={'CORE_AI_DATABASE_URL':f'postgresql://{ROLE}:{password}@127.0.0.1:{PGPORT}/{DATABASE}',
             'CORE_AI_ORIGIN':origin,'CORE_AI_MODEL_URL':model_url}
    # Save before creation so interruption can resume without resetting credentials.
    cfg.update(CORE_AI_ORIGIN=origin,CORE_AI_MODEL_URL=model_url)
    if 'CORE_AI_CONNECTION_REVEAL_KEY' not in cfg:
        material=run('/usr/bin/openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:3072',
                     stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
        cfg['CORE_AI_CONNECTION_REVEAL_KEY']=base64.b64encode(material).decode('ascii')
    write_private(ENV,''.join(f'{k}={v}\n' for k,v in cfg.items()))
    if not role_exists:
        pg(f"CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{password}';")
    if pg(f"SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication FROM pg_roles WHERE rolname='{ROLE}'")!='f':
        raise ValueError('CORE-AI database role has elevated permissions.')
    if not owner:
        pg(f'CREATE DATABASE {DATABASE} OWNER {ROLE};')
        pg(f'REVOKE ALL ON DATABASE {DATABASE} FROM PUBLIC;')
    pg('SELECT 1',password,DATABASE)
    return cfg

def site_import(original,caddyfile=CADDY,site=SITE):
    for line in original.splitlines():
        if not re.match(r'^\s*import\s+',line):
            continue
        tokens=shlex.split(line,comments=True)
        if len(tokens)!=2:
            continue
        pattern=tokens[1]
        if not os.path.isabs(pattern):
            pattern=str(caddyfile.parent/pattern)
        if fnmatch.fnmatch(str(site),pattern):
            return original
    return original.rstrip()+'\n\nimport '+str(site)+'\n'

def route_text(source,host):
    return MARKER+(source/'deploy/workstation.Caddyfile').read_text().replace('DOMAIN',domain(host),1)

def install_route(source,host):
    original=CADDY.read_text()
    old=SITE.read_text() if SITE.exists() else None
    if old is not None and not old.startswith('# Managed by CORE-AI'):
        raise ValueError('CORE-AI site file is not managed by this project.')
    if old is None:
        files=[CADDY,*CADDY.parent.glob('sites/*.caddy')]
        for f in files:
            if re.search(r'(?m)^\s*'+re.escape(host)+r'(?:\s|\{)',f.read_text()):
                raise ValueError('Domain already configured outside the managed CORE-AI site.')
    SITE.parent.mkdir(parents=True,exist_ok=True)
    SITE.write_text(route_text(source,host))
    CADDY.write_text(site_import(original))
    try:
        run('caddy','validate','--config',str(CADDY),'--adapter','caddyfile')
        run('systemctl','reload','caddy')
    except Exception:
        CADDY.write_text(original)
        if old is None:
            SITE.unlink(missing_ok=True)
        else:
            SITE.write_text(old)
        subprocess.run(['systemctl','reload','caddy'])
        raise

def backend_python(release,code,extra_env=None,stdin=None):
    env={k:v for k,v in os.environ.items() if not k.startswith('CORE_AI_')}
    env.update(load_env())
    env.update(extra_env or {})
    return run(str(release/'.venv/bin/python'),'-c',code,env=env,input=stdin,text=True)

def service_text(release,worker=False):
    command='-m core_ai.worker' if worker else f'-m uvicorn core_ai.api:app --host 127.0.0.1 --port {PORT} --proxy-headers --forwarded-allow-ips=127.0.0.1'
    return f'''# Managed by CORE-AI workstation
[Unit]
Description=CORE-AI {'durable task worker' if worker else 'workstation API'}
After=network-online.target postgresql@18-core_ai.service
Wants=network-online.target
Requires=postgresql@18-core_ai.service

[Service]
User=core-ai
Group=core-ai
WorkingDirectory={release}
EnvironmentFile={ENV}
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={release}/.venv/bin/python {command}
Restart=on-failure
RestartSec=3
TimeoutStopSec=40
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/core-ai
RestrictSUIDSGID=true
UMask=0077
MemoryMax={'1G' if worker else '768M'}
TasksMax=128

[Install]
WantedBy=multi-user.target
'''

def get_json(url):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=5) as response:
        return json.load(response)

def wait_ready():
    for _ in range(40):
        try:
            d=get_json(f'http://127.0.0.1:{PORT}/health')
            if d.get('project_id')=='core-ai' and d.get('database_connected'):
                try:
                    get_json(f'http://127.0.0.1:{PORT}/api/v1/projects')
                except urllib.error.HTTPError as e:
                    if e.code==401:
                        return
                raise ValueError('Anonymous project access was not rejected.')
        except (OSError,ValueError):
            time.sleep(.5)
    raise RuntimeError('CORE-AI health/authentication check failed. Routing was not switched.')

def backup(source):
    target=source/'backups'/('workstation-'+stamp())
    target.mkdir(parents=True,mode=0o700)
    os.chmod(target.parent,0o700)
    os.chown(target.parent,0,0)
    os.chmod(target,0o700)
    cfg=load_env()
    from urllib.parse import urlsplit
    u=urlsplit(cfg['CORE_AI_DATABASE_URL'])
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    env.update(PGPASSWORD=u.password,PGPASSFILE='/dev/null',PGCONNECT_TIMEOUT='5')
    dump=target/'core_ai.dump'
    with dump.open('wb') as output:
        run('/usr/lib/postgresql/18/bin/pg_dump','-w','-h','127.0.0.1','-p',str(PGPORT),'-U',ROLE,'-Fc',DATABASE,env=env,stdout=output)
    shutil.copy2(ENV,target/'workstation.env')
    if SITE.exists():
        shutil.copy2(SITE,target/'core-ai.caddy')
    (target/'release').write_text(str((BASE/'current').resolve())+'\n')
    print('Private PostgreSQL/config backup:',target)
    return target

def verify_backup(source):
    """Restore a fresh snapshot into an isolated temporary database, then drop it."""
    target=backup(source)
    temporary='core_ai_verify_'+secrets.token_hex(6)
    pg('CREATE DATABASE '+temporary+' OWNER '+ROLE)
    try:
        with (target/'core_ai.dump').open('rb') as incoming:
            run('runuser','-u','postgres','--','/usr/lib/postgresql/18/bin/pg_restore',
                '-w','-h','/var/run/postgresql','-p',str(PGPORT),'-d',temporary,
                '--exit-on-error','--no-owner','--no-privileges','--role='+ROLE,stdin=incoming)
        result=pg("SET ROLE "+ROLE+"; SELECT count(*) FROM schema_migrations; SELECT count(*) FROM users; SELECT count(*) FROM projects; SELECT count(*) FROM artifact_versions",database=temporary)
        (target/'restore-verification.txt').write_text('Restore succeeded in isolated database; application-role queries passed.\n'+result)
        print('PASS: backup restored and queried as the application role; live data was preserved.')
    finally:
        pg('DROP DATABASE '+temporary+' WITH (FORCE)')

def deploy(release,source,args):
    if not re.fullmatch(r'/opt/core-ai/releases/[A-Za-z0-9_-]+',str(release)) or not (release/'ui/index.html').is_file():
        raise ValueError('Build a CORE-AI release first.')
    oldcfg=load_env() if ENV.exists() else {}
    legacy=parse_env(source/'config.env') if (source/'config.env').exists() else {}
    host=domain(args.domain or oldcfg.get('CORE_AI_ORIGIN','').removeprefix('https://') or legacy.get('CORE_DOMAIN') or input('Dashboard domain: ').strip().lower())
    from urllib.parse import urlsplit
    model_host=args.model_host or urlsplit(oldcfg.get('CORE_AI_MODEL_URL','')).hostname or legacy.get('CORE_MODEL_HOST') or input('Private model-host IPv4: ').strip()
    if model_host=='host.docker.internal':
        model_host='127.0.0.1'
    model_url='http://'+str(ipaddress.IPv4Address(model_host))+':11434'
    if ENV.exists():
        backup(source)
    cfg=database_setup('https://'+host,model_url)
    cfg['CORE_AI_VPS_ENDPOINT']=args.endpoint or oldcfg.get('CORE_AI_VPS_ENDPOINT') or legacy.get('CORE_VPS_ENDPOINT') or input('Reachable VPS IPv4 or DNS name (WireGuard): ').strip()
    sys.path.insert(0,str(source/'scripts'))
    import network
    network.validate_endpoint(cfg['CORE_AI_VPS_ENDPOINT'])
    write_private(ENV,''.join(f'{k}={v}\n' for k,v in cfg.items()))
    if subprocess.run(['id','-u','core-ai'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        run('useradd','--system','--user-group','--home-dir','/var/lib/core-ai','--shell','/usr/sbin/nologin','core-ai')
    run('install','-d','-o','core-ai','-g','core-ai','-m','0700','/var/lib/core-ai')
    # Release becomes immutable to the application account before execution.
    run('chown','-R','root:root',str(release))
    backend_python(release,"from pathlib import Path; from core_ai import db; db.migrate(Path('"+str(release/ 'backend/sql')+"'))")
    count=pg('SELECT count(*) FROM users',cfg['CORE_AI_DATABASE_URL'].split(':',2)[2].split('@')[0],DATABASE)
    if count=='0':
        username=legacy.get('CORE_ADMIN_USERNAME') or input('CORE-AI administrator username: ').strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_@.\-]{1,63}',username):
            raise ValueError('Use 2–64 lowercase username characters.')
        password=legacy.get('CORE_ADMIN_PASSWORD')
        if not password:
            password=getpass.getpass('Administrator password (12+ characters): ')
            if password!=getpass.getpass('Repeat password: '):
                raise ValueError('Passwords did not match.')
        backend_python(release,"import sys,json; from core_ai import auth,db; x=json.load(sys.stdin); auth.seed(x['username'],x['password']); t,_=auth.login(x['username'],x['password']); db.query('DELETE FROM sessions WHERE token_hash=%s',(auth.token_hash(t),)); print('Administrator created; password verified.')",stdin=json.dumps({'username':username,'password':password}))
    # Only bootstrap defaults if no administrator has configured the provider.
    backend_python(release,"import os; from core_ai import db,models; x=db.query(\"SELECT key FROM settings WHERE key='inference'\",one=True); models.configure(os.environ['CORE_AI_MODEL_URL'],'qwen3:4b') if not x else None")
    # Keep the existing WireGuard interface/keys; fresh deployments can enroll the laptop.
    sys.path.insert(0,str(source/'scripts'))
    import network
    network.setup({})
    units=[Path('/etc/systemd/system/'+name+'.service') for name in ('core-ai-api','core-ai-worker')]
    for p in units:
        if p.exists() and not p.read_text().startswith(MARKER):
            raise ValueError('An unmanaged CORE-AI service exists; refusing to replace it.')
    if not units[0].exists():
        with socket.socket() as s:
            s.bind(('127.0.0.1',PORT))
    saved={p:p.read_bytes() if p.exists() else None for p in units}
    active={p:subprocess.run(['systemctl','is-active','--quiet',p.name]).returncode==0 for p in units}
    enabled={p:subprocess.run(['systemctl','is-enabled','--quiet',p.name]).returncode==0 for p in units}
    current=BASE/'current'
    web=Path('/var/www/core-ai-workstation')
    web.mkdir(parents=True,exist_ok=True)
    frontend=web/'current'
    for p in (current,frontend):
        if p.exists() and not p.is_symlink():
            raise ValueError('Managed release pointer is not a symlink.')
    previous={p:os.readlink(p) if p.is_symlink() else None for p in (current,frontend)}
    oldcaddy=CADDY.read_bytes()
    oldsite=SITE.read_bytes() if SITE.exists() else None
    archive=source/'backups'/('routing-'+stamp())
    archive.mkdir(parents=True,mode=0o700)
    os.chmod(archive.parent,0o700)
    os.chown(archive.parent,0,0)
    (archive/'Caddyfile').write_bytes(oldcaddy)
    if oldsite:
        (archive/'core-ai.caddy').write_bytes(oldsite)
    for p,body in saved.items():
        if body:
            (archive/p.name).write_bytes(body)
    try:
        for i,p in enumerate(units):
            p.write_text(service_text(release,worker=i==1))
        run('systemctl','daemon-reload')
        restart_after=datetime.datetime.now(datetime.timezone.utc).isoformat()
        run('systemctl','restart','core-ai-api','core-ai-worker')
        wait_ready()
        # Worker heartbeat proves queue service startup rather than only HTTP startup.
        for n in range(20):
            run('systemctl','is-active','--quiet','core-ai-worker')
            heartbeat=pg("SELECT count(*) FROM worker_status WHERE heartbeat>'"+restart_after+"'::timestamptz AND heartbeat>now()-interval '20 seconds'",cfg['CORE_AI_DATABASE_URL'].split(':',2)[2].split('@')[0],DATABASE)
            if heartbeat=='1':
                break
            if n==19:
                raise RuntimeError('Task worker did not become ready.')
            time.sleep(.5)
        for p,target in ((current,release),(frontend,release/'ui')):
            temp=p.with_name(p.name+'.next')
            temp.unlink(missing_ok=True)
            temp.symlink_to(target)
            os.replace(temp,p)
        install_route(source,host)
        run('systemctl','enable','core-ai-api','core-ai-worker')
    except Exception:
        CADDY.write_bytes(oldcaddy)
        if oldsite is None:
            SITE.unlink(missing_ok=True)
        else:
            SITE.write_bytes(oldsite)
        for p,old in previous.items():
            p.unlink(missing_ok=True)
            if old:
                p.symlink_to(old)
        for p,old in saved.items():
            subprocess.run(['systemctl','stop',p.name])
            if old is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(old)
        subprocess.run(['systemctl','daemon-reload'])
        for p in units:
            if active[p]:
                subprocess.run(['systemctl','start',p.name])
            if not enabled[p]:
                subprocess.run(['systemctl','disable',p.name])
        subprocess.run(['systemctl','reload','caddy'])
        raise
    # Stop only the superseded dashboards after cutover; preserve their volumes/data.
    if shutil.which('docker'):
        for name in ('core-ai-app-1','core-ai-webui-1'):
            result=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "com.docker.compose.project"}}',name],capture_output=True,text=True)
            if result.returncode==0 and result.stdout.strip()=='core-ai':
                run('docker','stop',name,stdout=subprocess.DEVNULL)
    print('CORE-AI custom workstation installed: https://'+host)
    print('Existing legacy data was retained as a private archive, not imported into the new database.')
    print('Run: ./core-ai doctor   then open the dashboard and submit a task.')

def main():
    if os.geteuid()!=0:
        raise ValueError('Use ./core-ai install or ./core-ai update as your normal user.')
    if sys.argv[1]=='admin':
        action=sys.argv[2]
        source=Path(sys.argv[3]).resolve()
        release=(BASE/'current').resolve()
        if action=='peer-add':
            sys.path.insert(0,str(source/'scripts'))
            import network
            cfg=load_env()
            info=network.add_peer({'CORE_VPS_ENDPOINT':cfg['CORE_AI_VPS_ENDPOINT']},sys.argv[4])
            runtime=source/'runtime'
            runtime.mkdir(mode=0o700,exist_ok=True)
            os.chown(runtime,source.stat().st_uid,source.stat().st_gid)
            export=runtime/'wireguard-public.json'
            export.write_text(json.dumps(info)+'\n')
            export.chmod(0o644)
        elif action=='set-login':
            import login as credentials
            password=getpass.getpass('New CORE-AI password (6+ characters): ')
            if password!=getpass.getpass('Repeat password: '):
                raise ValueError('Passwords did not match; no changes made.')
            prepared=credentials.prepare(sys.argv[4],password)
            backend_python(release,credentials.RESET_CODE,stdin=json.dumps(prepared))
        elif action=='backup':
            backup(source)
        elif action=='verify-backup':
            verify_backup(source)
        elif action=='publish':
            wait_ready()
            install_route(source,load_env()['CORE_AI_ORIGIN'].removeprefix('https://'))
            print('Caddy route validated and reloaded. Verify public HTTPS with ./core-ai doctor.')
        elif action=='test-model':
            backend_python(release,"from core_ai import models; import httpx; c=models.config(); r=httpx.post(c['endpoint']+'/api/generate',json={'model':c['model'],'prompt':'Reply with OK.','stream':False,'options':{'num_predict':32}},timeout=180,trust_env=False); r.raise_for_status(); x=r.json(); assert not x.get('error') and (x.get('response') or x.get('thinking')); print('PASS: model generation from native CORE-AI backend')")
        elif action=='doctor':
            wait_ready()
            print('CORE-AI API, database and anonymous-access protection: healthy')
            for service in ('core-ai-api','core-ai-worker'):
                run('systemctl','is-active',service)
            backend_python(release,"from core_ai import models,db; r=db.query(\"SELECT heartbeat>now()-interval '20 seconds' AS online FROM worker_status WHERE id='main'\",one=True); print('Worker heartbeat:', 'online' if r and r['online'] else 'OFFLINE'); x=models.list_models(); print('Ollama reachable; installed models:',len(x['models']))")
            cfg=load_env()
            try:
                result=get_json(cfg['CORE_AI_ORIGIN']+'/api/workstation')
                assert result['project_id']=='core-ai'
                print('Public HTTPS and CORE-AI identity: verified')
            except Exception:
                print('PENDING: public HTTPS. Check domain DNS and inbound TCP 80/443.')
        return
    parser=argparse.ArgumentParser()
    parser.add_argument('release',type=Path)
    parser.add_argument('source',type=Path)
    parser.add_argument('--domain')
    parser.add_argument('--model-host')
    parser.add_argument('--endpoint')
    args=parser.parse_args()
    deploy(args.release.resolve(),args.source.resolve(),args)

if __name__=='__main__':
    try:
        main()
    except (ValueError,RuntimeError,subprocess.CalledProcessError,OSError) as exc:
        sys.exit('STOP: '+str(exc))
