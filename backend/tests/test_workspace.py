"""Real PostgreSQL checks for file ingestion, revisions and access boundaries."""
import io
import json
import threading
import uuid
import httpx
from fastapi.testclient import TestClient
from core_ai import db,files,worker,models,agent_runtime
from core_ai.api import app

def account(signed,name='editor',role='EDITOR'):
    r=signed.post('/api/v1/access/users',json={'username':name,'password':'disposable-account-password','role':role})
    assert r.status_code==201,r.text
    c=TestClient(app,raise_server_exceptions=False)
    login=c.post('/api/v1/session',headers={'Origin':'http://testserver'},json={'username':name,'password':'disposable-account-password'})
    assert login.status_code==200,login.text
    c.headers.update({'Origin':'http://testserver','x-core-ai-csrf':login.json()['csrf']})
    return c,r.json()['id']

def test_files_are_processed_then_attached_and_versioned(signed,work):
    r=signed.post('/api/v1/files',data={'project_id':work['project_id']},files={'file':('memo.md',b'# Evidence\nliquidity improved','text/markdown')})
    assert r.status_code==201,r.text
    ident=r.json()['id']
    assert signed.get('/api/v1/files/'+ident).json()['status']=='QUEUED'
    files.process(files.claim())
    detail=signed.get('/api/v1/files/'+ident).json()
    assert detail['status']=='READY' and 'liquidity improved' in detail['text_content']
    assert 'raw' not in detail and detail['document_id']
    document=detail['document_id']
    assert len(signed.get('/api/v1/documents/'+document).json()['versions'])==1
    edit={'title':'Revised','content':'revised evidence','enabled':False,'expected_version':1}
    assert signed.put('/api/v1/documents/'+document,json=edit).json()['version']==2
    assert signed.put('/api/v1/documents/'+document,json=edit).status_code==409
    assert 'liquidity improved' in signed.get('/api/v1/documents/'+document+'?version=1').json()['content']
    chat=signed.post('/api/v1/chat/conversations',json={'model':work['model']}).json()['id']
    response=signed.post('/api/v1/chat/conversations/'+chat+'/messages',json={'content':'summarize','model':work['model'],'request_id':str(uuid.uuid4()),'file_ids':[ident]})
    assert response.status_code==201,response.text
    assert signed.get('/api/v1/chat/conversations/'+chat).json()['messages'][0]['attachments'][0]['file_id']==ident
    assert signed.get('/api/v1/files/'+ident+'/download').content==b'# Evidence\nliquidity improved'

def test_membership_and_global_readonly_are_enforced(signed,work):
    editor,editor_id=account(signed)
    viewer,viewer_id=account(signed,'viewer','VIEWER')
    try:
        assert editor.get('/api/v1/projects').json()==[]
        assert editor.get('/api/v1/documents?project_id='+work['project_id']).status_code==404
        assert signed.put('/api/v1/projects/'+work['project_id']+'/members',json={'username':'editor','role':'VIEWER'}).status_code==200
        assert editor.get('/api/v1/projects').json()[0]['member_role']=='VIEWER'
        assert editor.post('/api/v1/documents',json={'project_id':work['project_id'],'title':'bad','content':'no'}).status_code==403
        assert editor.put('/api/v1/models/config',json={'endpoint':'http://127.0.0.1:11434','model':'test:latest'}).status_code==403
        assert viewer.post('/api/v1/projects',json={'name':'forbidden'}).status_code==403
        assert viewer.post('/api/v1/files',files={'file':('a.txt',b'not permitted')}).status_code==403
        assert editor.get('/api/v1/access/users').status_code==403
        assert signed.put('/api/v1/projects/'+work['project_id']+'/members',json={'username':'editor','role':'EDITOR'}).status_code==200
        assert editor.post('/api/v1/documents',json={'project_id':work['project_id'],'title':'allowed','content':'yes'}).status_code==201
        assert signed.delete('/api/v1/projects/'+work['project_id']+'/members/'+editor_id).status_code==200
        assert editor.get('/api/v1/documents?project_id='+work['project_id']).status_code==404
    finally:editor.close();viewer.close()

def test_artifact_versions_sharing_and_conflicts(signed,work):
    editor,_=account(signed)
    try:
        body={'title':'Analysis','kind':'markdown','content':'original','project_id':work['project_id']}
        r=signed.post('/api/v1/library/artifacts',json=body)
        assert r.status_code==201,r.text
        ident=r.json()['id'];path='/api/v1/library/artifacts/'+ident
        assert editor.get(path).status_code==404
        signed.put('/api/v1/projects/'+work['project_id']+'/members',json={'username':'editor','role':'EDITOR'})
        assert editor.get(path).status_code==404 # private remains private
        update={**body,'visibility':'PROJECT','expected_version':1,'content':'shared revision'}
        assert signed.put(path,json=update).json()['version']==2
        assert signed.put(path,json=update).status_code==409
        assert editor.get(path).json()['can_edit']
        assert editor.put(path,json={**update,'expected_version':2,'content':'editor revision'}).json()['version']==3
        assert editor.put(path,json={**update,'expected_version':3,'visibility':'PRIVATE'}).status_code==403
        detail=signed.get(path).json()
        assert len(detail['versions'])==3 and detail['content']=='editor revision'
        assert signed.get(path+'?version=1').json()['content']=='original'
        assert signed.post('/api/v1/library/artifacts',json={'title':'Invalid','kind':'json','content':'invalid'}).status_code==422
    finally:editor.close()

def test_agent_selects_and_executes_only_authorized_tools(signed,work,monkeypatch):
    signed.put('/api/v1/agents/'+work['agent_id'],json={'name':'Tool agent','instructions':'Inspect then answer.','runtime_mode':'tools','tools':['project.inspect','artifact.create']})
    ident=signed.post('/api/v1/runs',json=work).json()['id'];run=worker.claim()
    real_client=httpx.Client;seen=[]
    def handler(request):
        body=json.loads(request.content);seen.append(body)
        if len(seen)==1:return httpx.Response(200,json={'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'project_inspect','arguments':{}}}]}})
        assert body['messages'][-1]['role']=='tool'
        return httpx.Response(200,json={'message':{'role':'assistant','content':'Project inspected.'},'done':True,'eval_count':5,'eval_duration':1000000000})
    monkeypatch.setattr(models,'inspect_model',lambda _: {'capabilities':['tools']})
    monkeypatch.setattr(agent_runtime.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler)))
    worker.execute(run)
    detail=signed.get('/api/v1/runs/'+ident).json()
    assert detail['status']=='SUCCEEDED' and detail['output']=='Project inspected.'
    assert any(s['tool']=='project.inspect' for s in detail['steps'])
    assert detail['metrics']['eval_count']==5
    try:agent_runtime.dispatch(run,'knowledge.search',{'query':'test'},4)
    except ValueError:pass
    else:raise AssertionError('Unselected tool was executed')

def test_model_without_tool_capability_is_rejected(signed,work,monkeypatch):
    signed.put('/api/v1/agents/'+work['agent_id'],json={'name':'Tools','instructions':'Inspect','runtime_mode':'tools','tools':['project.inspect']})
    signed.post('/api/v1/runs',json=work);run=worker.claim()
    monkeypatch.setattr(models,'inspect_model',lambda _: {'capabilities':['completion']})
    import pytest
    with pytest.raises(ValueError,match='tool support'):agent_runtime.execute(run,threading.Event())
