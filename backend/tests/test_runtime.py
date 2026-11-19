from concurrent.futures import ThreadPoolExecutor
import json
import httpx
from core_ai import db,worker,models

def test_agent_snapshot_and_cancel(signed,work):
    ident=signed.post('/api/v1/runs',json=work).json()['id']
    assert signed.put('/api/v1/agents/'+work['agent_id'],json={'name':'Analyst','instructions':'Changed instructions','enabled':True}).json()['version']==2
    detail=signed.get('/api/v1/runs/'+ident).json()
    assert detail['agent_version']==1 and detail['instructions']=='Answer with sources.'
    assert signed.post('/api/v1/runs/'+ident+'/cancel',json={}).json()['status']=='CANCELLED'
    assert signed.post('/api/v1/runs/'+ident+'/cancel',json={}).status_code==409

def test_queue_claim_serializes_and_recovers_expired(signed,work):
    ids=[signed.post('/api/v1/runs',json=work).json()['id'] for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:worker.claim(),range(2)))
    assert sum(r is not None for r in results)==1
    claimed=next(r for r in results if r)
    db.query("UPDATE runs SET lease_until=now()-interval '1 minute' WHERE id=%s",(claimed['id'],))
    next_run=worker.claim()
    assert next_run and str(next_run['id'])!=str(claimed['id'])
    assert db.query('SELECT status FROM runs WHERE id=%s',(claimed['id'],),one=True)['status']=='FAILED'

def test_project_scoped_retrieval_and_generation(signed,work,monkeypatch):
    other=signed.post('/api/v1/projects',json={'name':'Unrelated'}).json()['id']
    doc=signed.post('/api/v1/documents',json={'project_id':work['project_id'],'title':'liquidity','content':'liquidity is measured here'}).json()['id']
    signed.post('/api/v1/documents',json={'project_id':other,'title':'liquidity secret','content':'OTHER_PROJECT_SECRET liquidity'})
    ident=signed.post('/api/v1/runs',json=work).json()['id']
    run=worker.claim()
    real_client=httpx.Client
    seen=[]
    def handler(request):
        body=json.loads(request.content)
        system=body['messages'][0]['content']
        assert doc in system and 'OTHER_PROJECT_SECRET' not in system
        seen.append(body)
        return httpx.Response(200,text=json.dumps({'message':{'content':'Answer ['+doc+']'},'done':True})+'\n')
    monkeypatch.setattr(worker.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler)))
    worker.execute(run)
    detail=signed.get('/api/v1/runs/'+ident).json()
    assert detail['status']=='SUCCEEDED' and doc in detail['output']
    assert len(seen)==1
    assert [e['action'] for e in detail['events']]==['run.queued','run.started','tool.completed','tool.started','tool.completed','run.succeeded']
    assert doc in detail['events'][2]['detail']['sources']

def test_running_cancel_wins_over_output(signed,work):
    ident=signed.post('/api/v1/runs',json=work).json()['id']
    worker.claim()
    assert signed.post('/api/v1/runs/'+ident+'/cancel',json={}).json()['status']=='CANCEL_REQUESTED'
    worker.finish(ident,'SUCCEEDED',output='Late model output')
    detail=signed.get('/api/v1/runs/'+ident).json()
    assert detail['status']=='CANCELLED' and detail['output'] is None

def test_queue_limit_and_invalid_project(signed,work):
    broken={**work,'project_id':'00000000-0000-0000-0000-000000000000'}
    assert signed.post('/api/v1/runs',json=broken).status_code==404
    for _ in range(20):assert signed.post('/api/v1/runs',json=work).status_code==201
    assert signed.post('/api/v1/runs',json=work).status_code==409

def test_unreachable_provider_is_reported_not_faked(signed,monkeypatch):
    def fail():raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(models,'list_models',fail)
    r=signed.get('/api/v1/models').json()
    assert not r['available'] and r['models']==[]


def test_catalog_uses_reported_capabilities_without_hiding_unknown_models(signed,monkeypatch):
    monkeypatch.setattr(models,'list_models',lambda:{
        'available':True, 'config':{'model':'local:chat','endpoint':'http://127.0.0.1:11434'},
        'models':[{'name':'local:chat','digest':'a'},{'name':'local:vector','digest':'b'},{'name':'local:unknown'}],
    })
    def capabilities(endpoint,name,digest,window):
        return {'local:chat':['completion'],'local:vector':['embedding'],'local:unknown':None}[name]
    monkeypatch.setattr(models,'_catalog_capabilities',capabilities)
    result=signed.get('/api/v1/models?catalog=true').json()
    assert result['available'] is True
    assert {m['name']:m['capabilities'] for m in result['models']}=={
        'local:chat':['completion'],'local:vector':['embedding'],'local:unknown':None,
    }
