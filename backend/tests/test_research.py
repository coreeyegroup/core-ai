import json
import uuid

import httpx
import pytest

from core_ai import db, research, worker


def submit(signed, work, **spec):
    response = signed.post('/api/v1/runs', json={**work, 'research': {
        'success_criteria': 'Report the supported discrepancy and open questions.', **spec}})
    assert response.status_code == 201, response.text
    return '/api/v1/runs/' + response.json()['id']


def add_source(signed, work):
    response = signed.post('/api/v1/documents', json={
        'project_id': work['project_id'], 'title': 'Liquidity report',
        'content': 'Liquidity rose to 120 units during the period.'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def provider(monkeypatch, answer=None):
    calls = []
    real = httpx.Client

    def request(req):
        payload = json.loads(req.content)
        assert req.url.path == '/api/chat' and payload['format']['type'] == 'object'
        calls.append(payload)
        result = ({'queries': ['liquidity']} if payload['format']['title'] == 'Plan' else
                  (answer if answer is not None else {'findings': [
                      {'source': 1, 'statement': 'Liquidity was 120 units.',
                       'quote': 'Liquidity rose to 120 units during the period.'}],
                      'uncertainties': ['The excerpt did not disclose the unit definition.']}))
        return httpx.Response(200, json={'message': {'content': json.dumps(result)},
                                        'prompt_eval_count': 42, 'eval_count': 12})

    monkeypatch.setattr(research.httpx, 'Client', lambda **options: real(transport=httpx.MockTransport(request), **options))
    return calls


def test_research_plan_evidence_calculation_review_and_artifact(signed, work, monkeypatch):
    source = add_source(signed, work)
    another = signed.post('/api/v1/projects',json={'name':'Private other project'}).json()['id']
    signed.post('/api/v1/documents',json={'project_id':another,'title':'Liquidity','content':'Off-scope content.'})
    calls = provider(monkeypatch)
    path = submit(signed, work, calculations=[
        {'label':'Change','left':'100','operation':'percent_change','right':'120'}])
    worker.execute(worker.claim())
    run = signed.get(path).json()
    assert run['status'] == 'WAITING_REVIEW' and run['output'] is None
    state = run['research']
    assert state['calls'] == 2 and state['measured_input_tokens'] == 84 and len(calls) == 2
    assert state['evidence'][0]['id'] == source and state['evidence'][0]['version'] == 1
    assert 'Off-scope content' not in json.dumps(calls)
    assert 'percent_change(100, 120) = 20' in state['draft']
    assert signed.post(path+'/review', json={'decision':'approve','digest':'0'*64}).status_code == 409
    assert signed.post(path+'/review', json={'decision':'approve','digest':state['review_digest']}).status_code == 200
    assert signed.post(path+'/review', json={'decision':'approve','digest':state['review_digest']}).status_code == 409
    final = signed.get(path).json()
    assert final['status'] == 'SUCCEEDED' and final['output'] == state['draft']
    artifact = signed.get('/api/v1/library/artifacts/'+final['research']['artifact_id']).json()
    assert artifact['visibility'] == 'PRIVATE' and artifact['content'] == state['draft']


def test_checkpoint_recovery_fences_stale_attempt_and_preserves_plan(signed, work, monkeypatch):
    add_source(signed, work)
    calls = provider(monkeypatch)
    path = submit(signed, work, queries=['liquidity'], require_review=False)
    stale = worker.claim()
    orig_collect = research.collect
    with monkeypatch.context() as patch:
        patch.setattr(research, 'collect', lambda *_: (_ for _ in ()).throw(OSError('simulated worker death')))
        with pytest.raises(OSError):
            worker.execute(stale)
    assert research.collect == orig_collect
    assert signed.get(path).json()['research']['phase'] == 'COLLECT'
    db.query("UPDATE runs SET lease_until=now()-interval '1 second' WHERE id=%s", (stale['id'],))
    surviving = worker.claim()
    assert surviving['claim_token'] != stale['claim_token']
    worker.finish(stale['id'], 'FAILED', claim_token=stale['claim_token'])
    assert signed.get(path).json()['status'] == 'RUNNING'
    with pytest.raises(InterruptedError):
        worker.execute(stale)
    worker.execute(surviving)
    assert len(calls) == 1
    assert signed.get(path).json()['status'] == 'SUCCEEDED'


def test_pause_cancel_and_review_expiration(signed, work, monkeypatch):
    path = submit(signed, work, queries=['nothing'])
    first = worker.claim()
    assert signed.post(path+'/pause').json()['status'] == 'PAUSED'
    assert signed.post(path+'/resume').json()['status'] == 'QUEUED'
    second = worker.claim()
    assert second['claim_token'] != first['claim_token']
    assert signed.post(path+'/cancel').json()['status'] == 'CANCEL_REQUESTED'
    worker.finish(second['id'], 'FAILED', claim_token=second['claim_token'])
    assert signed.get(path).json()['status'] == 'CANCELLED'

    path = submit(signed, work, queries=['nothing'])
    worker.execute(worker.claim())
    state = signed.get(path).json()['research']
    db.query("UPDATE research_workflows SET review_expires_at=now() WHERE run_id=%s", (state['run_id'],))
    assert signed.post(path+'/review', json={'decision':'approve','digest':state['review_digest']}).status_code == 409
    worker.recover_tasks()
    assert signed.get(path).json()['status'] == 'CANCELLED'


def test_unverified_quote_and_revoked_authority_block_report(signed, work, monkeypatch):
    add_source(signed, work)
    provider(monkeypatch, {'findings':[{'source':1,'statement':'Fabricated finding.',
                                         'quote':'A quote that never appeared.'}]})
    path = submit(signed, work, queries=['liquidity'])
    run = worker.claim()
    with pytest.raises(ValueError, match='citation'):
        worker.execute(run)
    worker.finish(run['id'], 'FAILED', claim_token=run['claim_token'])
    assert signed.get(path).json()['research']['artifact_id'] is None

    path = submit(signed, work, queries=['missing'])
    worker.execute(worker.claim())
    state = signed.get(path).json()['research']
    db.query('UPDATE projects SET archived_at=now() WHERE id=%s', (work['project_id'],))
    assert signed.post(path+'/review', json={'decision':'approve','digest':state['review_digest']}).status_code == 409
    assert db.query('SELECT artifact_id FROM research_workflows WHERE run_id=%s',(uuid.UUID(path.rsplit('/',1)[-1]),),one=True)['artifact_id'] is None


def test_scheduled_research_waits_for_start_and_can_retry(signed, work):
    from datetime import datetime, timedelta, timezone

    future = (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
    path = submit(signed, work, scheduled_for=future, queries=['no evidence'])
    assert signed.get(path).json()['status'] == 'SCHEDULED'
    assert worker.claim_work() == (None, None)
    run_id = path.rsplit('/',1)[-1]
    db.query('UPDATE research_workflows SET scheduled_for=now() WHERE run_id=%s',(run_id,))
    kind, run = worker.claim_work()
    assert kind == 'task' and str(run['id']) == run_id
    worker.execute(run)
    assert signed.get(path).json()['status'] == 'WAITING_REVIEW'
    assert signed.post(path+'/cancel').status_code == 200
    retried = signed.post(path+'/retry')
    assert retried.status_code == 201
    assert signed.post(path+'/retry').json() == retried.json()
    retry = signed.get('/api/v1/runs/'+retried.json()['id']).json()
    assert retry['status'] == 'QUEUED' and retry['research']['scheduled_for'] is None


def test_source_revocation_stops_review(signed, work, monkeypatch):
    source = add_source(signed, work)
    provider(monkeypatch)
    path = submit(signed, work, queries=['liquidity'])
    worker.execute(worker.claim())
    state = signed.get(path).json()['research']
    db.query('UPDATE documents SET enabled=false WHERE id=%s', (source,))
    assert signed.post(path+'/review',json={'digest':state['review_digest'],'decision':'approve'}).status_code == 409
    assert signed.get(path).json()['research']['artifact_id'] is None


def test_project_editors_cannot_view_or_approve_another_users_research(signed, work):
    from test_workspace import account

    editor, _ = account(signed, 'research-editor')
    try:
        project = '/api/v1/projects/'+work['project_id']
        assert signed.put(project+'/members',json={'username':'research-editor','role':'EDITOR'}).status_code == 200
        path = submit(signed, work, queries=['missing'])
        worker.execute(worker.claim())
        draft = signed.get(path).json()['research']
        assert editor.get(path).status_code == 404
        assert editor.get('/api/v1/runs').json() == []
        assert editor.post(path+'/review',json={'digest':draft['review_digest'],'decision':'approve'}).status_code == 404
        assert editor.post(path+'/cancel').status_code == 404
        assert signed.get(path).json()['status'] == 'WAITING_REVIEW'
    finally:
        editor.close()
