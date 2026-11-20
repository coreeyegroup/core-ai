from concurrent.futures import ThreadPoolExecutor
import json

import httpx

from core_ai import db, worker

JOBS = '/api/v1/automation/jobs'


def create_connection(client, work):
    response = client.post('/api/v1/connections', json={
        'name': 'Daily workflow', 'project_id': work['project_id'],
        'agent_id': work['agent_id'], 'model': work['model'],
    })
    assert response.status_code == 201, response.text
    result = response.json()
    return result, {'Authorization': 'Bearer ' + result['token']}


def test_connection_submits_and_reads_only_its_own_jobs(signed, work, monkeypatch):
    connection, headers = create_connection(signed, work)
    _, other_headers = create_connection(signed, work)
    document = signed.post('/api/v1/documents', json={
        'project_id': work['project_id'], 'title': 'liquidity', 'content': 'Project source for analysis.',
    }).json()['id']
    other = signed.post('/api/v1/projects', json={'name': 'Other project'}).json()['id']
    signed.post('/api/v1/documents', json={
        'project_id': other, 'title': 'liquidity', 'content': 'Out-of-scope source.',
    })

    body = {'request_id': 'execution-1', 'prompt': 'liquidity'}
    # A signed-in browser session alone does not grant automation access.
    denied = signed.post(JOBS, json=body)
    assert denied.status_code == 401
    assert denied.headers['www-authenticate'] == 'Bearer'
    assert signed.post(JOBS, json={**body, 'project_id': other}, headers=headers).status_code == 422
    with ThreadPoolExecutor(max_workers=2) as pool:
        retries = list(pool.map(lambda _: signed.post(JOBS, json=body, headers=headers), range(2)))
    assert all(response.status_code == 202 for response in retries)
    job = retries[0].json()['id']
    assert retries[1].json()['id'] == job
    assert signed.post(JOBS, json={**body, 'prompt': 'Changed'}, headers=headers).status_code == 409
    assert signed.get(f'{JOBS}/{job}', headers=other_headers).status_code == 404
    assert signed.get(f'{JOBS}/{job}', headers=headers).json()['status'] == 'QUEUED'

    real_client = httpx.Client

    def provider(request):
        payload = json.loads(request.content)
        assert payload['model'] == work['model']
        system = payload['messages'][0]['content']
        assert document in system and 'Out-of-scope source.' not in system
        return httpx.Response(200, text=json.dumps({'message': {'content': 'Workflow result'}, 'done': True}) + '\n')

    monkeypatch.setattr(worker.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(provider)))
    run = worker.claim()
    assert str(run['id']) == job and run['runtime_mode'] == 'analysis'
    worker.execute(run)
    output = signed.get(f'{JOBS}/{job}', headers=headers).json()
    assert output['status'] == 'SUCCEEDED' and output['output'] == 'Workflow result'

    listing = signed.get('/api/v1/connections')
    assert len(listing.json()) == 2
    assert connection['token'] not in listing.text and 'token_hash' not in listing.text
    assert signed.post('/api/v1/connections/' + connection['id'] + '/revoke').status_code == 200
    assert signed.post(JOBS, json=body, headers=headers).status_code == 401
    assert signed.get(f'{JOBS}/{job}', headers=headers).status_code == 401


def test_connection_admin_csrf_and_analysis_scope(signed, work):
    body = {key: work[key] for key in ('project_id', 'agent_id', 'model')} | {'name': 'Restricted'}
    assert signed.post('/api/v1/connections', json=body, headers={'x-core-ai-csrf': ''}).status_code == 403
    _, headers = create_connection(signed, work)
    agent = '/api/v1/agents/' + work['agent_id']
    response = signed.put(agent, json={'name': 'Changed', 'instructions': 'Changed', 'runtime_mode': 'tools'})
    assert response.status_code == 200
    assert signed.post('/api/v1/connections', json=body).status_code == 422
    assert signed.post(JOBS, json={'request_id': 'job-1', 'prompt': 'Test'}, headers=headers).status_code == 422
    assert signed.get('/api/v1/connections').json()[0]['scope_available'] is False

    db.query("UPDATE users SET role='EDITOR' WHERE username='administrator'")
    assert signed.get('/api/v1/connections').status_code == 403
    assert signed.post('/api/v1/connections', json=body).status_code == 403
    assert signed.post(JOBS, json={'request_id': 'job-2', 'prompt': 'Test'}, headers=headers).status_code == 401


def test_direct_multi_model_jobs_and_optional_default(signed, monkeypatch):
    config = {'name': 'n8n local', 'model': 'local:chat', 'allowed_models': ['local:chat', 'local:code'],
              'allow_model_choice': True, 'max_output_tokens': 512}
    issued = signed.post('/api/v1/connections', json=config)
    assert issued.status_code == 201
    connection = issued.json()['id']
    headers = {'Authorization': 'Bearer ' + issued.json()['token']}
    assert signed.get('/api/v1/automation/models', headers=headers).json() == {
        'models': ['local:chat', 'local:code'], 'default': 'local:chat'}
    first = {'request_id': 'summarize', 'prompt': 'Summarize this'}
    second = {'request_id': 'code', 'prompt': 'Write code', 'model': 'local:code'}
    for body in (first, second):
        assert signed.post(JOBS, headers=headers, json=body).status_code == 202
    assert signed.post(JOBS, headers=headers, json={**second, 'model': 'local:chat'}).status_code == 409
    assert signed.post(JOBS, headers=headers, json={**second, 'request_id': 'other', 'model': 'different'}).status_code == 403

    real_client = httpx.Client
    seen = []
    def provider(request):
        payload = json.loads(request.content)
        seen.append(payload['model'])
        assert 'Project instructions' not in payload['messages'][0]['content']
        assert payload['options']['num_predict'] == 512
        return httpx.Response(200, text=json.dumps({'message': {'content': 'Done'}, 'done': True}) + '\n')

    monkeypatch.setattr(worker.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(provider)))
    for _ in range(2):
        run = worker.claim()
        assert run['project_id'] is None and run['agent_id'] is None
        worker.execute(run)
    assert seen == ['local:chat', 'local:code']
    activity = signed.get(f'/api/v1/connections/{connection}/activity').json()
    assert {item['request_id'] for item in activity} == {'code', 'summarize'}
    assert all(item['status'] == 'SUCCEEDED' and 'prompt' not in item and 'output' not in item for item in activity)
    assert signed.get(JOBS + '/' + activity[0]['id'], headers=headers).json()['output'] == 'Done'

    assert signed.put(f'/api/v1/connections/{connection}', json={**config, 'model': None}).status_code == 200
    assert signed.post(JOBS, headers=headers, json={**first, 'request_id': 'missing-model'}).status_code == 422
    assert signed.post(JOBS, headers=headers, json=first).status_code == 202


def test_connection_limits_permissions_pause_and_rotation(signed):
    config = {'name': 'Limited', 'model': 'local:chat', 'requests_per_minute': 1,
              'can_discover': False, 'can_read': False}
    issued = signed.post('/api/v1/connections', json=config).json()
    path = '/api/v1/connections/' + issued['id']
    headers = {'Authorization': 'Bearer ' + issued['token']}
    assert signed.get('/api/v1/automation/models', headers=headers).status_code == 403
    response = signed.post(JOBS, headers=headers, json={'request_id': 'first', 'prompt': 'Hello'})
    assert response.status_code == 202
    job = response.json()['id']
    assert signed.get(f'{JOBS}/{job}', headers=headers).status_code == 403
    limited = signed.post(JOBS, headers=headers, json={'request_id': 'second', 'prompt': 'Hello'})
    assert limited.status_code == 429 and limited.headers['retry-after']
    assert signed.put(path + '/pause', json={'paused': True}).status_code == 200
    assert signed.get(f'{JOBS}/{job}', headers=headers).status_code == 401
    assert signed.put(path + '/pause', json={'paused': False}).status_code == 200
    rotated = signed.post(path + '/rotate').json()
    assert signed.get(f'{JOBS}/{job}', headers=headers).status_code == 401
    new_headers = {'Authorization': 'Bearer ' + rotated['token']}
    assert signed.get(f'{JOBS}/{job}', headers=new_headers).status_code == 403
    assert signed.put(path, json={**config, 'expires_at': '2000-01-01T00:00:00Z'}).status_code == 200
    assert signed.get(f'{JOBS}/{job}', headers=new_headers).status_code == 401


def test_migration_preserves_existing_key_and_job(tmp_path, monkeypatch):
    from pathlib import Path
    from shutil import copyfile
    import os
    import uuid
    from psycopg.conninfo import make_conninfo
    from psycopg import sql
    from core_ai import auth

    schema = 'upgrade_' + uuid.uuid4().hex
    with db.connect() as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('CORE_AI_DATABASE_URL', make_conninfo(os.environ['CORE_AI_DATABASE_URL'],
                                                           options='-c search_path=' + schema))
    migrations = Path(__file__).resolve().parents[1] / 'sql'
    for initial in sorted(migrations.glob('*.sql'))[:5]:
        copyfile(initial, tmp_path / initial.name)
    db.migrate(tmp_path)
    auth.seed('upgrade-admin', 'disposable-upgrade-password')
    user = db.query('SELECT id FROM users', one=True)['id']
    project, agent, connection, job = [uuid.uuid4() for _ in range(4)]
    with db.connect() as conn:
        conn.execute('INSERT INTO projects(id,name,owner_id) VALUES (%s,%s,%s)', (project,'Project',user))
        conn.execute('INSERT INTO agents(id,name,instructions,owner_id) VALUES (%s,%s,%s,%s)', (agent,'Agent','Scope',user))
        conn.execute('INSERT INTO automation_connections(id,name,token_hash,project_id,agent_id,model,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                     (connection,'Existing','fixture-hash',project,agent,'local:existing',user))
        conn.execute("""
            INSERT INTO runs(id,project_id,agent_id,agent_version,instructions,prompt,model,status,requested_by,connection_id,request_id)
            VALUES (%s,%s,%s,1,'Scope','Prompt','local:existing','QUEUED',%s,%s,'first')
        """,(job,project,agent,user,connection))
    db.migrate(migrations)
    current = db.query('SELECT * FROM automation_connections WHERE id=%s',(connection,),one=True)
    assert current['allowed_models'] == ['local:existing'] and not current['allow_model_choice']
    assert (current['token_hash'],current['project_id'],current['agent_id']) == ('fixture-hash',project,agent)
    existing = db.query('SELECT status,connection_id,project_id,agent_id FROM runs WHERE id=%s',(job,),one=True)
    assert existing == {'status':'QUEUED','connection_id':connection,'project_id':project,'agent_id':agent}


def test_webhook_terminal_event_signature_and_delivery_status(signed, monkeypatch):
    import hashlib
    import hmac
    from core_ai import webhooks

    secret = 'fake-local-signing-secret-for-automated-tests'
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_URL','https://receiver.example/webhook')
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_SECRET',secret)
    monkeypatch.setenv('CORE_AI_WEBHOOK_INVALID_URL','http://receiver.example/webhook')
    monkeypatch.setenv('CORE_AI_WEBHOOK_INVALID_SECRET',secret)
    base = {'name':'Service','model':'local:chat','client_type':'platform'}
    assert signed.get('/api/v1/connections/webhook-destinations').json() == ['EVENTS']
    assert signed.post('/api/v1/connections',json={**base,'webhook_destination':'INVALID'}).status_code == 422
    issued = signed.post('/api/v1/connections',json={**base,'webhook_destination':'EVENTS'}).json()
    headers = {'Authorization':'Bearer '+issued['token']}
    body = {'request_id':'event-1','prompt':'private test prompt'}
    first = signed.post(JOBS,headers=headers,json=body).json()['id']
    assert signed.post(JOBS,headers=headers,json=body).json()['id'] == first
    assert webhooks.claim() is None
    assert str(worker.claim()['id']) == first
    worker.finish(first,'SUCCEEDED',output='private result')
    item = webhooks.claim()
    assert str(item['run_id']) == first and item['attempts'] == 1
    assert webhooks.claim() is None

    real_client = httpx.Client
    response_code = 503
    calls = []
    def receiver(request):
        calls.append(request.url)
        assert str(request.url) == 'https://receiver.example/webhook'
        assert 'authorization' not in request.headers
        assert b'private' not in request.content
        signed_bytes = request.headers['X-Core-AI-Timestamp'].encode()+b'.'+request.content
        assert request.headers['X-Core-AI-Signature'] == 'sha256='+hmac.new(secret.encode(),signed_bytes,hashlib.sha256).hexdigest()
        event = json.loads(request.content)
        assert event['type'] == 'job.finished' and event['id'] == first
        assert event['data']['request_id'] == 'event-1' and event['data']['status'] == 'SUCCEEDED'
        return httpx.Response(response_code,headers={'Location':'http://external.example/redirect'})

    monkeypatch.setattr(webhooks.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(receiver),**kwargs))
    assert webhooks.deliver(item,webhooks.destinations()) == 'PENDING'
    response_code = 302
    assert webhooks.deliver(item,webhooks.destinations()) == 'FAILED'
    assert len(calls) == 2
    response_code = 204
    assert webhooks.deliver(item,webhooks.destinations()) == 'DELIVERED'
    activity = signed.get(f"/api/v1/connections/{issued['id']}/activity").json()
    assert activity[0]['webhook_status'] == 'PENDING'
    assert 'token' not in activity[0] and 'webhook_url' not in activity[0]


def test_paused_connection_cancels_pending_webhook(signed, monkeypatch):
    from core_ai import webhooks

    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_URL','https://receiver.example/webhook')
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_SECRET','fake-local-signing-secret-for-automated-tests')
    issued = signed.post('/api/v1/connections',json={
        'name':'Sender','model':'local:chat','client_type':'webhook','webhook_destination':'EVENTS',
    }).json()
    headers = {'Authorization': 'Bearer '+issued['token']}
    first = signed.post(JOBS,headers=headers,json={'request_id':'pause-test','prompt':'test'}).json()['id']
    assert str(worker.claim()['id']) == first
    worker.finish(first,'FAILED',error='test error')
    assert signed.put(f"/api/v1/connections/{issued['id']}/pause",json={'paused':True}).status_code == 200
    assert webhooks.claim() is None
    assert signed.get(f"/api/v1/connections/{issued['id']}/activity").json()[0]['webhook_status'] == 'CANCELLED'


def test_recoverable_key_requires_reauthentication_and_stays_out_of_lists(signed, monkeypatch):
    import base64
    import subprocess

    private = subprocess.run(['/usr/bin/openssl','genpkey','-algorithm','RSA','-pkeyopt','rsa_keygen_bits:2048'],
                             capture_output=True,check=True).stdout
    monkeypatch.setenv('CORE_AI_CONNECTION_REVEAL_KEY',base64.b64encode(private).decode())
    assert signed.get('/api/v1/connections/key-storage').json() == {'available':True}
    created = signed.post('/api/v1/connections',json={'name':'Revealable','model':'local:chat','save_for_reveal':True}).json()
    path = '/api/v1/connections/'+created['id']
    row = db.query('SELECT token_hash,encrypted_token FROM automation_connections WHERE id=%s',(created['id'],),one=True)
    assert created['token'].encode() not in row['encrypted_token']
    listed = signed.get('/api/v1/connections').json()[0]
    assert listed['can_reveal'] and set(listed).isdisjoint({'token','token_hash','encrypted_token'})
    assert signed.post(path+'/reveal',json={'password':'wrong-password'}).status_code == 403
    revealed = signed.post(path+'/reveal',json={'password':'correct-password-123'})
    assert revealed.status_code == 200 and revealed.json()['token'] == created['token']
    assert revealed.headers['cache-control']=='no-store'
    assert signed.post(path+'/reveal',headers={'Origin':'https://other.example'},json={'password':'correct-password-123'}).status_code==403
    events = signed.get('/api/v1/events').json()
    assert any(event['action']=='connection.key_revealed' and event['detail']=={'id':created['id']} for event in events)
    assert created['token'] not in str(events)
    rotated = signed.post(path+'/rotate',json={'save_for_reveal':False})
    assert rotated.status_code==200
    assert signed.post(path+'/reveal',json={'password':'correct-password-123'}).status_code==409


def test_unavailable_webhook_does_not_close_other_edit_controls(signed, monkeypatch):
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_URL','https://receiver.example/webhook')
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_SECRET','fake-local-signing-secret-for-automated-tests')
    original = {'name':'Service','model':'local:chat','webhook_destination':'EVENTS'}
    created = signed.post('/api/v1/connections',json=original)
    assert created.status_code==201
    monkeypatch.delenv('CORE_AI_WEBHOOK_EVENTS_URL')
    updated=signed.put('/api/v1/connections/'+created.json()['id'],json={**original,'name':'Renamed','requests_per_minute':9})
    assert updated.status_code==200
    row=signed.get('/api/v1/connections').json()[0]
    assert (row['name'],row['requests_per_minute'],row['webhook_destination'])==('Renamed',9,'EVENTS')


def test_dynamic_model_scope_and_policies_follow_the_catalog(signed, monkeypatch):
    from core_ai import connections

    catalog = ['one:latest', 'two:latest', 'blocked:latest']
    monkeypatch.setattr(connections, 'installed_models', lambda operation: catalog)
    body = {'name': 'Dynamic', 'model_access': 'all', 'allow_model_choice': True, 'context_tokens': 4096,
            'model_policies': {'blocked:latest': {'enabled': False}, 'one:latest': {
                'requests_per_minute': 1, 'timeout_seconds': 30, 'max_output_tokens': 512, 'context_tokens': 2048}}}
    created = signed.post('/api/v1/connections', json=body)
    assert created.status_code == 201
    key = created.json()
    headers = {'Authorization': 'Bearer ' + key['token']}
    assert signed.get('/api/v1/automation/models', headers=headers).json() == {
        'models': ['one:latest', 'two:latest'], 'default': None}
    policies = signed.get('/api/v1/automation/model-policies', headers=headers).json()['limits']
    assert policies['one:latest']['context_tokens'] == 2048
    assert policies['two:latest']['context_tokens'] == 4096

    def submit(ident, model):
        return signed.post(JOBS, headers=headers, json={'request_id': ident, 'prompt': 'Check', 'model': model})

    assert submit('blocked', 'blocked:latest').status_code == 403
    first = submit('first', 'one:latest')
    assert first.status_code == 202
    assert submit('first', 'one:latest').json() == first.json()
    assert submit('second', 'one:latest').status_code == 429
    assert submit('other', 'two:latest').status_code == 202
    catalog.append('new:latest')
    assert submit('new', 'new:latest').status_code == 202
    catalog.remove('two:latest')
    assert submit('removed', 'two:latest').status_code == 403
    effective = db.query('SELECT timeout_seconds,max_output_tokens,context_tokens FROM runs WHERE id=%s',
                         (first.json()['id'],), one=True)
    assert effective == {'timeout_seconds': 30, 'max_output_tokens': 512, 'context_tokens': 2048}
    usage = signed.get('/api/v1/automation/usage', headers=headers)
    assert usage.status_code == 200
    assert {row['model']: row['pending'] for row in usage.json()['models']} == {
        'one:latest': 1, 'two:latest': 1, 'new:latest': 1}

    update = signed.put('/api/v1/connections/' + key['id'], json={'name': 'Legacy editor', 'allow_model_choice': True})
    assert update.status_code == 200
    selected = signed.get('/api/v1/connections').json()[0]
    assert selected['model_access'] == 'all' and selected['context_tokens'] == 4096
    assert selected['model_policies'] == body['model_policies']


def test_job_cancel_retry_admin_webhook_replay_and_schema(signed, monkeypatch):
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_URL', 'https://receiver.example/webhook')
    monkeypatch.setenv('CORE_AI_WEBHOOK_EVENTS_SECRET', 'x' * 32)
    response = signed.post('/api/v1/connections', json={'name': 'Cancellation', 'model': 'test',
        'can_cancel': True, 'webhook_destination': 'EVENTS'})
    assert response.status_code == 201
    connection = response.json()
    headers = {'Authorization': 'Bearer ' + connection['token']}
    result = signed.post(JOBS, headers=headers, json={'request_id': 'cancelled', 'prompt': 'Hello'})
    ident = result.json()['id']
    uri = f'{JOBS}/{ident}'
    assert signed.post(uri+'/cancel', headers=headers).json() == {'status': 'CANCELLED'}
    assert signed.post(uri+'/cancel', headers=headers).json() == {'status': 'CANCELLED'}
    assert signed.post(uri+'/retry', headers=headers, json={'request_id': 'cancelled'}).status_code == 409
    retry = signed.post(uri+'/retry', headers=headers, json={'request_id': 'retry'})
    assert retry.status_code == 202 and retry.json()['id'] != ident
    assert signed.post(uri+'/retry', headers=headers, json={'request_id': 'retry'}).json() == retry.json()
    scoped = '/api/v1/connections/' + connection['id'] + '/jobs/' + ident
    db.query("UPDATE automation_webhook_deliveries SET status='FAILED',attempts=3 WHERE run_id=%s", (ident,))
    assert signed.post(scoped+'/webhook/replay').status_code == 202
    assert signed.post(scoped+'/webhook/replay').status_code == 409
    assert db.query("SELECT attempts FROM automation_webhook_deliveries WHERE run_id=%s", (ident,), one=True)['attempts'] == 0
    schema = signed.get('/api/v1/automation/openapi.json')
    assert schema.status_code == 200
    assert set(schema.json()['paths']) >= {JOBS, JOBS+'/{ident}/cancel', '/api/v1/automation/usage'}
    assert all(path.startswith('/api/v1/automation/') for path in schema.json()['paths'])


def test_workspace_capacity_reservation_and_alternating_claim(signed, work, monkeypatch):
    monkeypatch.setenv('CORE_AI_QUEUE_CAPACITY', '3')
    monkeypatch.setenv('CORE_AI_WORKSPACE_QUEUE_RESERVE', '1')
    _, headers = create_connection(signed, work)
    for i in range(2):
        assert signed.post(JOBS, headers=headers, json={'request_id': str(i), 'prompt': 'Queue'}).status_code == 202
    assert signed.post(JOBS, headers=headers, json={'request_id': 'limit', 'prompt': 'Queue'}).status_code == 409
    interactive = signed.post('/api/v1/runs', json=work)
    assert interactive.status_code == 201
    kind, job = worker.claim_work()
    assert kind == 'automation'
    worker.finish(job['id'], 'FAILED')
    kind, job = worker.claim_work(last_automation=True)
    assert kind == 'task' and str(job['id']) == interactive.json()['id']


def test_connection_cancel_permission_and_ownership(signed, work):
    _, headers = create_connection(signed, work)
    response = signed.post(JOBS, headers=headers, json={'request_id': 'own', 'prompt': 'Queue'})
    uri = JOBS + '/' + response.json()['id'] + '/cancel'
    assert signed.post(uri, headers=headers).status_code == 403
    response = signed.post('/api/v1/connections', json={'name': 'Other key', 'model': 'test', 'can_cancel': True})
    other = {'Authorization': 'Bearer ' + response.json()['token']}
    assert signed.post(uri, headers=other).status_code == 404


def test_embeddings_are_separately_scoped_metered_and_retry_safe(signed, monkeypatch):
    from core_ai import connections

    monkeypatch.setattr(connections, 'installed_models', lambda op: ['embed:latest'] if op == 'embedding' else ['chat:latest'])
    create = signed.post('/api/v1/connections', json={'name': 'Embeddings', 'model_access': 'all',
        'allow_model_choice': True, 'can_embed': True, 'can_submit': False})
    assert create.status_code == 201
    headers = {'Authorization': 'Bearer ' + create.json()['token']}
    assert signed.get('/api/v1/automation/models?operation=embedding', headers=headers).json()['models'] == ['embed:latest']
    body = {'request_id': 'embedding', 'model': 'embed:latest', 'input': 'search query'}
    endpoint = '/api/v1/automation/embeddings'
    assert signed.post(endpoint, headers=headers, json={**body, 'model': 'chat:latest'}).status_code == 403
    assert signed.post(JOBS, headers=headers, json={'request_id': 'chat', 'model': 'chat:latest', 'prompt': 'Test'}).status_code == 403
    first = signed.post(endpoint, headers=headers, json=body)
    assert first.status_code == 202
    assert signed.post(endpoint, headers=headers, json=body).json() == first.json()
    real_client = httpx.Client

    def provider(request):
        assert request.url.path == '/api/embed'
        params = json.loads(request.content)
        assert params['input'] == 'search query' and params['model'] == 'embed:latest' and not params['truncate']
        return httpx.Response(200, json={'embeddings': [[0.5, -0.25, 0.125]], 'prompt_eval_count': 3})

    monkeypatch.setattr(worker.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(provider)))
    run = worker.claim()
    assert run['operation'] == 'embedding'
    worker.execute(run)
    result = signed.get(f"{JOBS}/{first.json()['id']}", headers=headers).json()
    assert result['status'] == 'SUCCEEDED' and result['embeddings'] == [[0.5, -0.25, 0.125]]
    usage = signed.get('/api/v1/automation/usage', headers=headers).json()['models'][0]
    assert usage['measured_input_tokens'] == 3 and usage['measured_output_tokens'] == 0


def test_key_rotation_overlap_can_be_ended_before_expiry(signed, work):
    connection, original = create_connection(signed, work)
    path = '/api/v1/connections/' + connection['id']
    rotated = signed.post(path+'/rotate', json={'overlap_minutes': 15})
    assert rotated.status_code == 200 and rotated.json()['overlap_until']
    current = {'Authorization': 'Bearer ' + rotated.json()['token']}
    models_url = '/api/v1/automation/models'
    assert signed.get(models_url, headers=original).status_code == 200
    assert signed.get(models_url, headers=current).status_code == 200
    assert signed.post(path+'/end-overlap').status_code == 200
    assert signed.get(models_url, headers=original).status_code == 401
    assert signed.get(models_url, headers=current).status_code == 200
