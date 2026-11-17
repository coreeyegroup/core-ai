"""Git-managed open-source AI deployment and WireGuard enrollment."""
import argparse
import datetime
import getpass
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import fnmatch
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import network

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'config.env'
CADDYFILE = Path('/etc/caddy/Caddyfile')
CADDYSITE = Path('/etc/caddy/sites/core-ai.caddy')
CADDYBACKUPS = Path('/var/backups/core-ai')
API = 'http://127.0.0.1:3101/api'


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def docker(*args, **kwargs):
    return run(['sudo', 'docker', *args], **kwargs)


def compose(*args, **kwargs):
    # Never interpolate a legacy .env containing passwords or provider secrets.
    return docker('compose', '--env-file', '/dev/null', '-f', str(ROOT / 'compose.yaml'), *args, **kwargs)


def parse_config(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.startswith('#'))


def read_config():
    if not ENV.exists():
        raise ValueError('Run ./core-ai migrate for the previous deployment, or ./core-ai install for a fresh setup.')
    return parse_config(ENV.read_text())


def write_private(path, text):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.env-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_domain(value):
    value = value.strip().lower()
    labels = value.split('.')
    if len(value) > 253 or len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        raise ValueError('Enter a DNS name such as ai.example.com, without a scheme or path.')
    return value


def validate_model_host(value):
    if value == 'host.docker.internal':
        return value
    address = ipaddress.IPv4Address(value.strip())
    if not any(address in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Use the private WireGuard model address or host.docker.internal for later VPS inference.')
    return str(address)


def site_import_config(original, caddyfile, site):
    """Import only our site; preserve imports that already cover it."""
    for line in original.splitlines():
        if not re.match(r'^\s*import\s+', line):
            continue
        tokens = shlex.split(line, comments=True)
        if len(tokens) != 2:
            continue
        pattern = tokens[1]
        if not os.path.isabs(pattern):
            pattern = str(caddyfile.parent / pattern)
        if fnmatch.fnmatch(str(site), pattern):
            return original
    # A new wildcard would load unrelated sites that may already be individually
    # imported. An exact path avoids duplicate definitions for those sites.
    return original.rstrip() + '\n\nimport ' + str(site) + '\n'


def configure(args):
    old = read_config() if ENV.exists() else {}
    legacy = parse_config((ROOT / '.env').read_text()) if (ROOT / '.env').exists() else {}
    previous_domain = old.get('CORE_DOMAIN') or urllib.parse.urlsplit(legacy.get('WEBUI_URL', '')).hostname or ''
    domain = validate_domain(args.domain or previous_domain or input('Dashboard domain: '))
    endpoint = network.validate_endpoint(args.endpoint or old.get('CORE_VPS_ENDPOINT') or input('Reachable VPS IPv4 or DNS name: '))
    host = validate_model_host(args.model_host or old.get('CORE_MODEL_HOST') or network.CLIENT_IP)
    username = old.get('CORE_ADMIN_USERNAME') or legacy.get('WEBUI_ADMIN_EMAIL') or input('Administrator username: ').strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9_@.\-]{1,63}', username):
        raise ValueError('Username must start with a lowercase letter and use 2-64 lowercase letters, digits, @, dots, underscores or hyphens.')
    password = old.get('CORE_ADMIN_PASSWORD') or legacy.get('WEBUI_ADMIN_PASSWORD')
    if not password:
        password = getpass.getpass('Administrator password (12+ characters): ')
        if password != getpass.getpass('Repeat password: '):
            raise ValueError('Passwords did not match.')
    if len(password) < 12 or len(password.encode()) > 72 or '\n' in password or '\r' in password:
        raise ValueError('Use 12+ characters, at most 72 UTF-8 bytes, and no line breaks.')
    config = {
        'CORE_DOMAIN': domain,
        'CORE_VPS_ENDPOINT': endpoint,
        'CORE_MODEL_HOST': host,
        'CORE_ADMIN_USERNAME': username,
        'CORE_ADMIN_PASSWORD': password,
        'CORE_CHAT_MODEL': args.model or old.get('CORE_CHAT_MODEL') or 'qwen3:4b',
        'CORE_EMBED_MODEL': args.embedding_model or old.get('CORE_EMBED_MODEL') or 'nomic-embed-text:latest',
        'CORE_JWT_SECRET': old.get('CORE_JWT_SECRET') or secrets.token_hex(32),
        'CORE_SIG_KEY': old.get('CORE_SIG_KEY') or secrets.token_hex(32),
        'CORE_SIG_SALT': old.get('CORE_SIG_SALT') or secrets.token_hex(32),
        'CORE_BOOTSTRAP_TOKEN': old.get('CORE_BOOTSTRAP_TOKEN') or secrets.token_hex(32),
    }
    for key in ('CORE_CHAT_MODEL', 'CORE_EMBED_MODEL'):
        if not re.fullmatch(r'[A-Za-z0-9_.:/-]+', config[key]):
            raise ValueError('Invalid model name.')
    write_private(ENV, ''.join(f'{k}={v}\n' for k, v in config.items()))
    app_config = {
        'SERVER_PORT': '3001', 'STORAGE_DIR': '/app/server/storage',
        'JWT_SECRET': config['CORE_JWT_SECRET'], 'SIG_KEY': config['CORE_SIG_KEY'],
        'SIG_SALT': config['CORE_SIG_SALT'], 'AUTH_TOKEN': config['CORE_BOOTSTRAP_TOKEN'],
        'LLM_PROVIDER': 'ollama', 'OLLAMA_BASE_PATH': f'http://{host}:11434',
        'OLLAMA_MODEL_PREF': config['CORE_CHAT_MODEL'], 'OLLAMA_MODEL_TOKEN_LIMIT': '4096',
        'EMBEDDING_ENGINE': 'ollama', 'EMBEDDING_BASE_PATH': f'http://{host}:11434',
        'EMBEDDING_MODEL_PREF': config['CORE_EMBED_MODEL'], 'VECTOR_DB': 'lancedb',
        'DISABLE_TELEMETRY': 'true', 'DISABLE_SWAGGER_DOCS': 'true',
        'COMMUNITY_HUB_BUNDLE_DOWNLOADS_ENABLED': 'false',
    }
    runtime = ROOT / 'runtime'
    runtime.mkdir(mode=0o700, exist_ok=True)
    # AnythingLLM owns its persistent dotenv file so UI provider changes can persist.
    # Only an explicit configure command overwrites managed provider defaults.
    with tempfile.NamedTemporaryFile(mode='w') as handle:
        handle.write(''.join(f'{k}={json.dumps(v)}\n' for k, v in app_config.items()))
        handle.flush()
        run(['sudo', 'install', '-o', '1000', '-g', '1000', '-m', '0600', handle.name, str(runtime / 'anythingllm.env')])
    print('Local configuration saved. Credentials and encryption secrets were preserved.')


def http_json(url, timeout=10, data=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def wait_ready():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            if http_json(API + '/ping', 5).get('online'):
                return
        except (OSError, ValueError):
            pass
        time.sleep(3)
    raise ValueError('Dashboard did not become healthy in 5 minutes. Run ./core-ai logs; the existing HTTPS route was not changed.')


def verify_admin():
    config = read_config()
    source = "const {User}=require('./models/user'); const {SystemSettings}=require('./models/systemSettings'); (async()=>{const u=await User.get({username:process.argv[1]});if(!u||u.role!=='admin'||u.suspended||!await SystemSettings.isMultiUserMode())process.exit(2);process.exit(0)})().catch(()=>process.exit(2))"
    compose('exec', '-T', '-w', '/app/server', 'app', 'node', '-e', source, config['CORE_ADMIN_USERNAME'], stdout=subprocess.DEVNULL)
    # Also prove that anonymous access to workspace data is rejected.
    try:
        http_json(API + '/workspaces')
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            return
        raise
    raise ValueError('Anonymous workspace access was not rejected; publishing is blocked.')


def bootstrap_admin():
    config = read_config()
    mode = http_json(API + '/system/multi-user-mode')
    if not mode.get('multiUserMode'):
        session = http_json(API + '/request-token', data={'password': config['CORE_BOOTSTRAP_TOKEN']})
        if not session.get('valid') or not session.get('token'):
            raise ValueError('Private bootstrap authentication failed; existing credentials were not reset.')
        result = http_json(API + '/system/enable-multi-user', data={'username': config['CORE_ADMIN_USERNAME'], 'password': config['CORE_ADMIN_PASSWORD']}, token=session['token'])
        if not result.get('success'):
            raise ValueError('Administrator creation failed. Inspect local logs; public route was not changed.')
    verify_admin()


def running_ids(service):
    result = docker('ps', '--filter', 'label=com.docker.compose.project=core-ai', '--filter', f'label=com.docker.compose.service={service}', '--format', '{{.ID}}', capture_output=True, text=True)
    return result.stdout.split()


def archive(label, members, containers):
    destination = ROOT / 'backups'
    destination.mkdir(mode=0o700, exist_ok=True)
    os.chmod(destination, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'{label}-{stamp}.tar.gz'
    if containers:
        docker('stop', *containers)
    try:
        run(['sudo', 'tar', '-czf', str(target), '-C', str(ROOT), *members])
        run(['sudo', 'chown', f'{os.getuid()}:{os.getgid()}', str(target)])
        os.chmod(target, 0o600)
    finally:
        if containers:
            docker('start', *containers)
    print('Consistent private backup saved:', target.name)
    return target


def backup():
    read_config()
    members = ['config.env', 'compose.yaml', 'runtime']
    if (ROOT / 'data-anythingllm').exists():
        members.append('data-anythingllm')
    return archive('core-ai', members, running_ids('app'))


def legacy_backup():
    marker = ROOT / 'runtime/legacy-backup.done'
    if marker.exists() and (ROOT / 'runtime/migration-complete').exists():
        return
    members = [name for name in ('.env', 'data') if (ROOT / name).exists()]
    if not members:
        raise ValueError('No legacy data/settings found. Use install for a fresh deployment.')
    # Capture the previous image, mounts and effective environment in a private archive.
    result = docker('ps', '-a', '--filter', 'label=com.docker.compose.project=core-ai', '--filter', 'label=com.docker.compose.service=webui', '--format', '{{.ID}}', capture_output=True, text=True)
    ids = result.stdout.split()
    if ids:
        inspected = docker('inspect', *ids, capture_output=True, text=True).stdout
        write_private(ROOT / 'runtime/legacy-container.json', inspected)
        members.append('runtime/legacy-container.json')
    target = archive('before-open-source-migration', members, running_ids('webui'))
    write_private(marker, target.name + '\n')


def deploy(with_backup=False):
    read_config()
    run(['sudo', '-v'])
    if not (ROOT / 'runtime/anythingllm.env').exists():
        raise ValueError('Application configuration missing. Run ./core-ai configure.')
    run(['sudo', 'install', '-d', '-o', '1000', '-g', '1000', '-m', '0700', str(ROOT / 'data-anythingllm')])
    compose('config', '--quiet')
    if with_backup:
        backup()
    compose('pull')
    # Keep the legacy dashboard until the new application and authentication pass.
    compose('up', '-d', '--force-recreate', 'app')
    wait_ready()
    bootstrap_admin()
    print('AnythingLLM healthy; administrator and anonymous-access protection verified.')


def publish():
    config = read_config()
    domain = validate_domain(config['CORE_DOMAIN'])
    wait_ready()
    verify_admin()
    caddyfile = CADDYFILE
    site = CADDYSITE
    original = run(['sudo', 'cat', str(caddyfile)], capture_output=True, text=True).stdout
    exists = subprocess.run(['sudo', 'test', '-e', str(site)]).returncode == 0
    previous_site = run(['sudo', 'cat', str(site)], capture_output=True, text=True).stdout if exists else None
    marker = '# Managed by CORE-AI\n'
    if previous_site is not None and not previous_site.startswith(marker):
        raise ValueError('Existing core-ai.caddy is not managed by this installer; refusing to overwrite it.')
    adapted = run(['sudo', 'caddy', 'adapt', '--config', str(caddyfile), '--adapter', 'caddyfile'], capture_output=True, text=True)
    existing_json = json.loads(adapted.stdout)
    def contains_host(value):
        if isinstance(value, dict):
            return domain in value.get('host', []) or any(contains_host(v) for v in value.values())
        return isinstance(value, list) and any(contains_host(v) for v in value)
    if not exists and contains_host(existing_json):
        raise ValueError('The requested domain already exists in Caddy. Review its existing route before taking ownership.')
    candidate = site_import_config(original, caddyfile, site)
    snippet = marker + domain + ' {\n    reverse_proxy 127.0.0.1:3101\n}\n'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_dir = CADDYBACKUPS / stamp
    run(['sudo', 'mkdir', '-p', str(backup_dir), str(site.parent)])
    run(['sudo', 'cp', '-a', str(caddyfile), str(backup_dir / 'Caddyfile')])
    if exists:
        run(['sudo', 'cp', '-a', str(site), str(backup_dir / 'core-ai.caddy')])
    def write_root(path, text):
        with tempfile.NamedTemporaryFile(mode='w') as handle:
            handle.write(text)
            handle.flush()
            run(['sudo', 'install', '-m', '0644', handle.name, str(path)])
    try:
        write_root(site, snippet)
        if candidate != original:
            write_root(caddyfile, candidate)
        run(['sudo', 'caddy', 'validate', '--config', str(caddyfile), '--adapter', 'caddyfile'])
        run(['sudo', 'systemctl', 'reload', 'caddy'])
    except (OSError, subprocess.CalledProcessError):
        run(['sudo', 'cp', '-a', str(backup_dir / 'Caddyfile'), str(caddyfile)])
        if exists:
            run(['sudo', 'cp', '-a', str(backup_dir / 'core-ai.caddy'), str(site)])
        else:
            run(['sudo', 'rm', '-f', str(site)])
        subprocess.run(['sudo', 'systemctl', 'reload', 'caddy'])
        raise
    print('Caddy route installed:', ('https://' + domain))
    try:
        http_json(('https://' + domain) + '/api/ping', 15)
        print('PASS: public HTTPS health endpoint.')
    except (OSError, ValueError):
        print('PENDING: public HTTPS check. Point domain DNS to this VPS and allow inbound 80/443; then run ./core-ai publish.')


def doctor():
    network.doctor()
    if not ENV.exists():
        print('New application is not configured; use migrate/install.')
        return
    config = read_config()
    try:
        http_json(API + '/ping', 5)
        print('Dashboard: healthy on localhost:3101')
    except (OSError, ValueError):
        print('Dashboard: not reachable on localhost:3101')
    host = config['CORE_MODEL_HOST']
    try:
        if host == 'host.docker.internal':
            print('VPS inference selected; use test-model for a container-side check.')
        else:
            models = http_json(f'http://{host}:11434/api/tags', 10).get('models', [])
            print('Ollama model-list endpoint reachable; model count:', len(models))
    except (OSError, ValueError):
        print('Model connection pending. Run the Windows WireGuard setup and check UDP 51820 reachability.')


def test_model(model):
    config = read_config()
    model = model or config['CORE_CHAT_MODEL']
    source = """require('dotenv').config(); const model=process.argv[1]; (async()=>{const r=await fetch(process.env.OLLAMA_BASE_PATH+'/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,prompt:'Reply with OK.',stream:false,options:{num_predict:32}}),signal:AbortSignal.timeout(180000)});const j=await r.json();if(!r.ok||j.error||!(j.response||j.thinking))process.exit(2);console.log('PASS: model generation from dashboard container');})().catch(()=>process.exit(2));"""
    compose('exec', '-T', '-w', '/app/server', 'app', 'node', '-e', source, model)


def migrate(args):
    legacy_backup()
    existing = read_config() if ENV.exists() else {}
    mapping = {'domain':'CORE_DOMAIN', 'endpoint':'CORE_VPS_ENDPOINT', 'model_host':'CORE_MODEL_HOST', 'model':'CORE_CHAT_MODEL', 'embedding_model':'CORE_EMBED_MODEL'}
    if not ENV.exists() or any(getattr(args, option) and getattr(args, option) != existing.get(key) for option, key in mapping.items()):
        configure(args)
    network.setup(read_config())
    deploy()
    publish()
    legacy = running_ids('webui')
    if legacy:
        docker('stop', *legacy)
    write_private(ROOT / 'runtime/migration-complete', 'AnythingLLM active; legacy data retained.\n')
    print('Migration complete. Previous dashboard data and container were retained, not converted.')
    doctor()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['help', 'install', 'migrate', 'configure', 'deploy', 'publish', 'doctor', 'status', 'logs', 'backup', 'infra-update', 'test-model', 'peer-add'])
    parser.add_argument('--domain')
    parser.add_argument('--endpoint')
    parser.add_argument('--model-host')
    parser.add_argument('--backup', action='store_true')
    parser.add_argument('--model')
    parser.add_argument('--embedding-model')
    parser.add_argument('--public-key')
    args = parser.parse_args()
    if args.action == 'help':
        parser.print_help()
        print('Use ./core-ai update to fast-forward Git, back up state and redeploy.')
    elif args.action == 'install':
        if (ROOT / '.env').exists() and not ENV.exists():
            raise ValueError('Previous deployment detected. Use ./core-ai migrate --endpoint VPS_ADDRESS.')
        configure(args)
        network.setup(read_config())
        deploy()
        publish()
        doctor()
    elif args.action == 'migrate':
        migrate(args)
    elif args.action == 'configure':
        configure(args)
    elif args.action == 'deploy':
        deploy(args.backup)
        doctor()
    elif args.action == 'publish':
        publish()
    elif args.action in ('doctor', 'status'):
        doctor()
    elif args.action == 'logs':
        compose('logs', '--tail', '100', 'app')
    elif args.action == 'backup':
        backup()
    elif args.action == 'infra-update':
        print('Infrastructure package update completed. Other host packages were not upgraded.')
    elif args.action == 'test-model':
        test_model(args.model)
    elif args.action == 'peer-add':
        if not args.public_key:
            raise ValueError('--public-key is required.')
        network.add_peer(read_config(), args.public_key)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        print('STOP:', str(error), file=sys.stderr)
        sys.exit(2)
