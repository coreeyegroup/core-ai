"""Small deployment CLI; only Python's standard library is required."""
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

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / '.env'
CADDYFILE = Path('/etc/caddy/Caddyfile')
CADDYSITE = Path('/etc/caddy/sites/core-ai.caddy')
CADDYBACKUPS = Path('/var/backups/core-ai')


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def docker(*args, **kwargs):
    return run(['sudo', 'docker', *args], **kwargs)


def compose(*args, **kwargs):
    # Disable automatic .env interpolation: env_file raw passes passwords literally.
    return docker('compose', '--env-file', '/dev/null', '-f', str(ROOT / 'compose.yaml'), *args, **kwargs)


def read_config():
    if not ENV.exists():
        raise ValueError('Run ./core-ai configure first.')
    return dict(line.split('=', 1) for line in ENV.read_text().splitlines() if '=' in line and not line.startswith('#'))


def validate_domain(value):
    value = value.strip().lower()
    labels = value.split('.')
    if len(value) > 253 or len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        raise ValueError('Enter a DNS name such as ai.example.com, without a scheme or path.')
    return value


def validate_model_host(value):
    address = ipaddress.IPv4Address(value.strip())
    if address not in ipaddress.IPv4Network('100.64.0.0/10'):
        raise ValueError('Use the laptop Tailscale IPv4 address.')
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
    previous_domain = urllib.parse.urlsplit(old.get('WEBUI_URL', '')).hostname or ''
    previous_host = urllib.parse.urlsplit(old.get('OLLAMA_BASE_URL', '')).hostname or ''
    domain = validate_domain(args.domain or input(f'Dashboard domain [{previous_domain}]: ').strip() or previous_domain)
    host = validate_model_host(args.model_host or input(f'Laptop Tailscale IPv4 [{previous_host}]: ').strip() or previous_host)
    email = (old.get('WEBUI_ADMIN_EMAIL') or input('Administrator email: ').strip()).lower()
    if not re.fullmatch(r'[^\s=@]+@[^\s=@]+\.[^\s=@]+', email):
        raise ValueError('Enter a valid administrator email.')
    password = old.get('WEBUI_ADMIN_PASSWORD')
    if not password:
        password = getpass.getpass('Administrator password (12+ characters): ')
        if password != getpass.getpass('Repeat password: '):
            raise ValueError('Passwords did not match.')
        if len(password) < 12 or len(password.encode()) > 72 or '\n' in password or '\r' in password:
            raise ValueError('Use at least 12 characters, at most 72 UTF-8 bytes, with no line breaks.')
    config = {
        'WEBUI_URL': f'https://{domain}',
        'OLLAMA_BASE_URL': f'http://{host}:11434',
        'WEBUI_ADMIN_EMAIL': email,
        'WEBUI_ADMIN_PASSWORD': password,
        'WEBUI_SECRET_KEY': old.get('WEBUI_SECRET_KEY') or secrets.token_hex(32),
        'WEBUI_AUTH': 'true',
        'ENABLE_SIGNUP': 'false',
        'ENABLE_INITIAL_ADMIN_SIGNUP': 'false',
        'DEFAULT_USER_ROLE': 'pending',
        'ENABLE_OPENAI_API': 'false',
        'ENABLE_OLLAMA_API': 'true',
        'ENABLE_PERSISTENT_CONFIG': 'false',
    }
    fd, temporary = tempfile.mkstemp(prefix='.env-', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(''.join(f'{key}={value}\n' for key, value in config.items()))
        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('Local configuration saved; existing credentials and application secret preserved.')


def http_json(url, timeout=10):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.load(response)


def wait_ready():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            http_json('http://127.0.0.1:3100/health', 5)
            return
        except (OSError, ValueError):
            time.sleep(3)
    raise ValueError('Dashboard did not become healthy in 5 minutes. Run ./core-ai logs; HTTPS was not changed.')


def verify_admin():
    source = "import os,sqlite3; c=sqlite3.connect('file:/app/backend/data/webui.db?mode=ro',uri=True); n=c.execute('SELECT count(*) FROM user WHERE role=? AND email=?',('admin',os.environ['WEBUI_ADMIN_EMAIL'])).fetchone()[0]; raise SystemExit(0 if n else 2)"
    compose('exec', '-T', 'webui', 'python', '-c', source, stdout=subprocess.DEVNULL)


def backup():
    read_config()
    destination = ROOT / 'backups'
    destination.mkdir(mode=0o700, exist_ok=True)
    os.chmod(destination, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'core-ai-{stamp}.tar.gz'
    running = bool(compose('ps', '--status', 'running', '-q', 'webui', capture_output=True, text=True).stdout.strip())
    if running:
        compose('stop', 'webui')
    try:
        members = ['.env', 'compose.yaml'] + (['data'] if (ROOT / 'data').exists() else [])
        run(['sudo', 'tar', '-czf', str(target), '-C', str(ROOT), *members])
        run(['sudo', 'chown', f'{os.getuid()}:{os.getgid()}', str(target)])
        os.chmod(target, 0o600)
    finally:
        if running:
            compose('start', 'webui')
    print('Consistent backup saved:', target.name)


def deploy(with_backup=False):
    read_config()
    run(['sudo', '-v'])
    compose('config', '--quiet')
    if with_backup:
        backup()
    compose('pull')
    compose('up', '-d', '--remove-orphans')
    wait_ready()
    verify_admin()
    print('Dashboard healthy; configured administrator verified. Signup is closed.')


def publish():
    config = read_config()
    domain = validate_domain(urllib.parse.urlsplit(config['WEBUI_URL']).hostname or '')
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
    snippet = marker + domain + ' {\n    reverse_proxy 127.0.0.1:3100\n}\n'
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
    print('Caddy route installed:', config['WEBUI_URL'])
    try:
        http_json(config['WEBUI_URL'] + '/health', 15)
        print('PASS: public HTTPS health endpoint.')
    except (OSError, ValueError):
        print('PENDING: public HTTPS check. Point domain DNS to this VPS and allow inbound 80/443; then run ./core-ai publish.')


def doctor():
    status = run(['tailscale', 'status', '--json'], capture_output=True, text=True)
    info = json.loads(status.stdout)
    print('Tailscale:', info.get('BackendState'))
    print('Active tailnet:', (info.get('CurrentTailnet') or {}).get('Name', 'unknown'))
    print('Visible peers:', len(info.get('Peer') or {}))
    if info.get('BackendState') != 'Running':
        print('ACTION: sudo tailscale up (complete the account sign-in link).')
    if ENV.exists():
        config = read_config()
        host = urllib.parse.urlsplit(config['OLLAMA_BASE_URL']).hostname
        result = subprocess.run(['bash', str(ROOT / 'scripts/check-connection.sh'), host], cwd=ROOT)
        if result.returncode:
            print('Model connection pending. Run the Git-managed Windows setup on the laptop using this same tailnet.')
        try:
            http_json('http://127.0.0.1:3100/health', 5)
            print('Dashboard: healthy on localhost:3100')
        except (OSError, ValueError):
            print('Dashboard: not reachable on localhost:3100')


def test_model(model):
    if not model:
        raise ValueError('Supply --model with an installed chat model name.')
    code = """import json,os,sys,urllib.request
payload=json.dumps({'model':sys.argv[1],'prompt':'Reply with OK.','stream':False,'options':{'num_predict':32}}).encode()
request=urllib.request.Request(os.environ['OLLAMA_BASE_URL']+'/api/generate',data=payload,headers={'Content-Type':'application/json'})
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(request,timeout=180) as response: result=json.load(response)
if result.get('error') or not (result.get('response') or result.get('thinking')): raise SystemExit('Model did not return generated text.')
print('PASS: generation from the dashboard container; model:',sys.argv[1])
"""
    compose('exec', '-T', 'webui', 'python', '-c', code, model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['help', 'install', 'configure', 'deploy', 'publish', 'doctor', 'status', 'logs', 'backup', 'infra-update', 'test-model'])
    parser.add_argument('--domain')
    parser.add_argument('--model-host')
    parser.add_argument('--backup', action='store_true')
    parser.add_argument('--model')
    args = parser.parse_args()
    if args.action == 'help':
        parser.print_help()
        print('Use ./core-ai update to fast-forward Git, back up state and redeploy.')
    elif args.action == 'install':
        configure(args)
        deploy()
        publish()
        doctor()
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
        compose('logs', '--tail', '100', 'webui')
    elif args.action == 'backup':
        backup()
    elif args.action == 'infra-update':
        print('Infrastructure package update completed. Other host packages were not upgraded.')
    elif args.action == 'test-model':
        test_model(args.model)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        print('STOP:', str(error), file=sys.stderr)
        sys.exit(2)
