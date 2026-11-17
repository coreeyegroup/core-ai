"""Direct two-peer WireGuard; private keys never leave their own device."""
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

INTERFACE = 'coreai'
CONFIG = Path('/etc/wireguard/coreai.conf')
MARKER = '# Managed by CORE-AI WireGuard\n'
SERVER_IP = '10.203.0.1'
CLIENT_IP = '10.203.0.2'
PORT = 51820


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def validate_key(value):
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ValueError('Invalid WireGuard public key.') from None
    if len(decoded) != 32 or base64.b64encode(decoded).decode() != value:
        raise ValueError('Invalid WireGuard public key.')
    return value


def validate_endpoint(value):
    value = value.strip().lower()
    try:
        address = ipaddress.IPv4Address(value)
        if address.is_unspecified or address.is_loopback or address.is_multicast:
            raise ValueError('Use the reachable VPS address.')
        return str(address)
    except ipaddress.AddressValueError:
        if len(value) > 253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
            raise ValueError('Use a VPS IPv4 address or DNS name without scheme, port or path.')
        return value


def render(private_key, peer=None):
    validate_key(private_key)
    text = MARKER + f'[Interface]\nAddress = {SERVER_IP}/32\nListenPort = {PORT}\nPrivateKey = {private_key}\n'
    if peer:
        text += f'\n[Peer]\nPublicKey = {validate_key(peer)}\nAllowedIPs = {CLIENT_IP}/32\n'
    return text


def read_existing():
    if subprocess.run(['sudo', 'test', '-e', str(CONFIG)]).returncode:
        return None
    text = run(['sudo', 'cat', str(CONFIG)], capture_output=True, text=True).stdout
    if not text.startswith(MARKER):
        raise ValueError('Existing coreai.conf is not owned by CORE-AI; refusing to replace it.')
    return text


def field(text, key):
    match = re.search(r'^' + re.escape(key) + r'\s*=\s*(\S+)\s*$', text, re.M)
    return match.group(1) if match else None


def write_config(text):
    run(['sudo', 'install', '-d', '-m', '0700', '/etc/wireguard'])
    with tempfile.NamedTemporaryFile(mode='w') as handle:
        handle.write(text)
        handle.flush()
        run(['sudo', 'install', '-m', '0600', handle.name, str(CONFIG)])


def apply(text, old):
    if text != old:
        write_config(text)
    try:
        if text != old:
            run(['sudo', 'systemctl', 'restart', f'wg-quick@{INTERFACE}'])
        run(['sudo', 'systemctl', 'enable', '--now', f'wg-quick@{INTERFACE}'], stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        if old:
            write_config(old)
            subprocess.run(['sudo', 'systemctl', 'restart', f'wg-quick@{INTERFACE}'])
        else:
            subprocess.run(['sudo', 'systemctl', 'stop', f'wg-quick@{INTERFACE}'])
        raise


def setup(config):
    old = read_existing()
    private_key = field(old, 'PrivateKey') if old else run(['wg', 'genkey'], capture_output=True, text=True).stdout.strip()
    if not private_key:
        raise ValueError('Existing managed tunnel has no private key. It was not replaced.')
    peer = field(old, 'PublicKey') if old else None
    apply(render(private_key, peer), old)
    if subprocess.run(['sh', '-c', 'command -v ufw >/dev/null 2>&1']).returncode == 0:
        status = run(['sudo', 'ufw', 'status'], capture_output=True, text=True).stdout
        if 'Status: active' in status:
            run(['sudo', 'ufw', 'allow', f'{PORT}/udp', 'comment', 'CORE-AI WireGuard'])
    print(f'WireGuard ready on UDP {PORT}; allow this port in the VPS provider firewall if enabled.')


def add_peer(config, key):
    key = validate_key(key)
    old = read_existing()
    if not old:
        raise ValueError('Run the Ubuntu install/migrate command before enrolling the laptop.')
    private_key = field(old, 'PrivateKey')
    existing = field(old, 'PublicKey')
    public = run(['wg', 'pubkey'], input=private_key + '\n', capture_output=True, text=True).stdout.strip()
    if key == public:
        raise ValueError('The laptop must have its own key.')
    if existing and existing != key:
        raise ValueError('A different laptop is already enrolled; existing peer was preserved.')
    apply(render(private_key, key), old)
    info = public_info(public, config['CORE_VPS_ENDPOINT'])
    print(json.dumps(info))
    return info


def public_info(public_key, endpoint):
    """Export only public routing data; never a private tunnel configuration."""
    return {'server_public_key': validate_key(public_key), 'endpoint': validate_endpoint(endpoint), 'port': PORT, 'server_ip': SERVER_IP, 'client_ip': CLIENT_IP}


def doctor():
    result = subprocess.run(['sudo', 'wg', 'show', INTERFACE, 'latest-handshakes'], capture_output=True, text=True)
    if result.returncode:
        print('WireGuard tunnel not active; run ./core-ai install or ./core-ai migrate.')
        return
    rows = result.stdout.strip().splitlines()
    if not rows:
        print('WireGuard: no laptop enrolled. Run the Windows setup script.')
        return
    import time
    latest = max(int(row.split()[-1]) for row in rows)
    if latest == 0:
        print('WireGuard: laptop enrolled, no handshake yet. Check Windows service and VPS UDP reachability.')
    else:
        print(f'WireGuard: last laptop handshake {int(time.time()) - latest} seconds ago.')
