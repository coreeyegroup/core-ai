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
