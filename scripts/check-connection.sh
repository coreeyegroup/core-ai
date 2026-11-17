#!/usr/bin/env bash
# Read-only check. No model inference or machine configuration changes.
set -eu
if [ "$#" -ne 1 ]; then
  printf 'Usage: bash scripts/check-connection.sh LAPTOP_TAILSCALE_IPV4\n' >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf 'MISSING: python3\n' >&2
  exit 2
fi
python3 - "$1" <<'PY'
import ipaddress
import json
import subprocess
import sys
import urllib.error
import urllib.request

def fail(message):
    print(message, file=sys.stderr)
    sys.exit(2)

try:
    address = ipaddress.IPv4Address(sys.argv[1])
except ipaddress.AddressValueError:
    fail('Supply the current laptop Tailscale IPv4 address.')
if address not in ipaddress.IPv4Network('100.64.0.0/10'):
    fail('Expected a Tailscale IPv4 address within 100.64.0.0/10.')
try:
    result = subprocess.run(['tailscale', 'status', '--json'], capture_output=True, text=True, timeout=15, check=True)
    status = json.loads(result.stdout)
except (OSError, subprocess.SubprocessError, ValueError):
    fail('Unable to read Tailscale status. Check tailscale status on this host.')

print('Backend state:', status.get('BackendState', 'unknown'))
print('Active tailnet:', (status.get('CurrentTailnet') or {}).get('Name', 'unknown'))
print('This device:', (status.get('Self') or {}).get('HostName', 'unknown'))
if status.get('BackendState') != 'Running':
    fail('Tailscale is not running and authenticated. Resolve its reported state first.')
peers = list((status.get('Peer') or {}).values())
print('Visible peer count:', len(peers))
for peer in peers:
    print('Peer:', peer.get('HostName', 'unknown'), ','.join(peer.get('TailscaleIPs') or []), 'online=' + str(peer.get('Online', 'unknown')))
target = next((p for p in peers if str(address) in (p.get('TailscaleIPs') or [])), None)
if target is None:
    fail('Laptop is not a visible peer. Compare active tailnets and review approval, expiry and access policy before changing Ollama.')
print('Laptop peer found; checking private Ollama API.')
# A direct private endpoint must not be sent through an HTTP proxy.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open('http://' + str(address) + ':11434/api/tags', timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        fail('Unexpectedly large model-list response.')
    models = json.loads(raw).get('models')
    if not isinstance(models, list) or not models:
        fail('Ollama returned no model list. Confirm existing models on Windows.')
    print('Model-list API reachable. Models:', len(models))
    for model in models:
        print('-', model.get('name', '(unnamed)'))
except (OSError, urllib.error.URLError, ValueError, AttributeError):
    fail('Ollama API unavailable or invalid. With peer visibility established, inspect the Windows listener, scoped firewall and Tailscale port access.')
print('PASS: host-to-laptop model listing. Inference and dashboard-container access still need verification.')
PY
