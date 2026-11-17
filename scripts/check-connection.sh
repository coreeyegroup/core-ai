#!/usr/bin/env bash
set -euo pipefail
[ "$#" -eq 1 ] || { printf 'Usage: bash scripts/check-connection.sh PRIVATE_MODEL_IPV4\n' >&2; exit 2; }
python3 - "$1" <<'PY'
import ipaddress, json, sys, urllib.request
try:
    address=ipaddress.IPv4Address(sys.argv[1])
    if not any(address in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
        raise ValueError('Use an RFC1918 private model address.')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://{address}:11434/api/tags',timeout=10) as response:
        models=json.load(response).get('models',[])
    if not models: raise ValueError('No models returned.')
    print('PASS: private Ollama model list; count:',len(models))
    for model in models: print('-',model.get('name','(unnamed)'))
except (OSError,ValueError) as error:
    print('Model endpoint unavailable:',str(error),file=sys.stderr)
    sys.exit(2)
PY
