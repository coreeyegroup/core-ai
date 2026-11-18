#!/usr/bin/env bash
# Disposable GitHub runner ONLY: exercise the native installer with test credentials.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true ]] || { echo 'This smoke test is restricted to disposable CI runners.' >&2; exit 1; }
cd "$(dirname "$0")/.."
# Reuse verified Actions toolcache runtimes in this disposable test environment.
# Real installs download/build independent copies through install-infra.sh.
sudo install -d -m 0755 /opt/core-ai/toolchain
sudo ln -s "$(dirname "$(dirname "$(command -v node)")")" /opt/core-ai/toolchain/node-v26.13.0
sudo ln -s "$(python -c 'import sys; print(sys.base_prefix)')" /opt/core-ai/toolchain/python-3.14.10
umask 077
cat > config.env <<'CONFIG'
CORE_DOMAIN=ai.example.invalid
CORE_VPS_ENDPOINT=203.0.113.1
CORE_MODEL_HOST=127.0.0.1
CORE_ADMIN_USERNAME=ci-admin
CORE_ADMIN_PASSWORD=disposable-ci-password-123
CONFIG
./core-ai install --domain ai.example.invalid --endpoint 203.0.113.1 --model-host 127.0.0.1
curl --fail --silent http://127.0.0.1:18787/health | python -c "import sys,json; x=json.load(sys.stdin); assert x['project_id']=='core-ai' and x['database_connected']; print('Native API and PostgreSQL healthy')"
sudo systemctl is-active --quiet core-ai-api core-ai-worker
# Verify login, authenticated access and CSRF using the real installed systemd API.
python - <<'PY'
import json,urllib.request,urllib.error
base='http://127.0.0.1:18787/api/v1/'
r=urllib.request.urlopen(urllib.request.Request(base+'session',data=json.dumps({'username':'ci-admin','password':'disposable-ci-password-123'}).encode(),headers={'Content-Type':'application/json','Origin':'https://ai.example.invalid'}))
cookie=r.headers['Set-Cookie'].split(';',1)[0]
session=json.load(r)
req=urllib.request.Request(base+'projects',headers={'Cookie':cookie})
assert json.load(urllib.request.urlopen(req))==[]
req=urllib.request.Request(base+'projects',data=json.dumps({'name':'Native smoke test'}).encode(),headers={'Cookie':cookie,'Content-Type':'application/json','Origin':'https://ai.example.invalid','x-core-ai-csrf':session['csrf']})
assert 'id' in json.load(urllib.request.urlopen(req))
print('Real native login, CSRF-protected write and database persistence passed')
PY
./core-ai backup
# Reinstall/update path must preserve the administrator, provider config and records.
./core-ai install --domain ai.example.invalid --endpoint 203.0.113.1 --model-host 127.0.0.1
sudo -u postgres /usr/lib/postgresql/18/bin/psql -X -p 5434 -d core_ai -Atc "SELECT count(*) FROM projects WHERE name='Native smoke test'" | python -c "import sys; assert sys.stdin.read().strip()=='1'; print('Repeated install preserved project data')"
# A local credential reset must work without rebuilding the installed application.
printf 'abc123\nabc123\n' | ./core-ai set-login --username ci-renamed
python - <<'PY'
import json,urllib.request
req=urllib.request.Request('http://127.0.0.1:18787/api/v1/session',data=json.dumps({'username':'ci-renamed','password':'abc123'}).encode(),headers={'Content-Type':'application/json','Origin':'https://ai.example.invalid'})
assert json.load(urllib.request.urlopen(req))['username']=='ci-renamed'
print('Local credential reset works against the installed API without rebuilding')
PY
