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
./core-ai verify-backup
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
# Exercise the actual installed queue worker against a deterministic local provider.
python tests/ollama_fixture.py > /tmp/core-ai-provider-fixture.log 2>&1 &
TASK_PROVIDER_PID=$!
trap 'kill "$TASK_PROVIDER_PID" 2>/dev/null || true' EXIT
python - <<'PY'
import json,time,uuid,urllib.request
base='http://127.0.0.1:18787/api/v1/'
headers={'Content-Type':'application/json','Origin':'https://ai.example.invalid'}
def call(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    r=urllib.request.urlopen(req,timeout=5)
    if path=='session':headers['Cookie']=r.headers['Set-Cookie'].split(';',1)[0]
    return json.load(r)
s=call('session',{'username':'ci-renamed','password':'abc123'});headers['x-core-ai-csrf']=s['csrf']
c=call('chat/conversations',{'model':'qwen3:4b','title':'Native chat verification'})
call('chat/conversations/'+c['id']+'/messages',{'model':'qwen3:4b','content':'Verify persisted streaming','request_id':str(uuid.uuid4())})
partial=False
for _ in range(150):
    reply=call('chat/conversations/'+c['id'])['messages'][-1]
    partial=partial or bool(reply['content'] and reply['status']=='RUNNING')
    if reply['status']=='COMPLETE':
        assert reply['content']=='Deterministic streamed CI reply.'
        assert partial,'A partial streamed reply was not observed'
        print('Native chat: real API, queue worker, incremental persistence and completed reply verified')
        break
    assert reply['status']!='FAILED',reply
    time.sleep(.1)
else:raise AssertionError('Native chat worker did not complete')
# Real file processing, source persistence, revisions and model-directed tools.
project=call('projects')[0]['id']
boundary='core-ai-disposable-upload'
payload=('--'+boundary+'\r\nContent-Disposition: form-data; name="project_id"\r\n\r\n'+project+'\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="evidence.md"\r\nContent-Type: text/markdown\r\n\r\n# Evidence\nMeasured native file ingestion.\r\n--'+boundary+'--\r\n').encode()
h={**headers,'Content-Type':'multipart/form-data; boundary='+boundary}
f=json.load(urllib.request.urlopen(urllib.request.Request(base+'files',data=payload,headers=h)))
for _ in range(150):
    detail=call('files/'+f['id'])
    if detail['status']=='READY':break
    assert detail['status']!='FAILED',detail
    time.sleep(.1)
else:raise AssertionError('File worker did not complete')
assert detail['document_id'] and 'Measured native' in detail['text_content']
artifact=call('library/artifacts',{'title':'Native revision test','content':'First version','project_id':project})
body={'title':'Native revision test','content':'Second version','project_id':project,'expected_version':1}
req=urllib.request.Request(base+'library/artifacts/'+artifact['id'],data=json.dumps(body).encode(),headers=headers,method='PUT')
assert json.load(urllib.request.urlopen(req))['version']==2
assert call('library/artifacts/'+artifact['id']+'?version=1')['content']=='First version'
agent=call('agents',{'name':'Native tool agent','instructions':'Inspect the project and answer.','runtime_mode':'tools','tools':['project.inspect']})
task=call('runs',{'project_id':project,'agent_id':agent['id'],'prompt':'Inspect this project','model':'qwen3:4b'})
for _ in range(150):
    result=call('runs/'+task['id'])
    if result['status']=='SUCCEEDED':break
    assert result['status'] not in ('FAILED','CANCELLED'),result
    time.sleep(.1)
else:raise AssertionError('Tool task did not complete')
assert any(step['tool']=='project.inspect' for step in result['steps'])
print('Native file processing, source creation, artifact revisions and model-directed tool execution verified')

PY
