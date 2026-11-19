import json
import threading
import uuid
import httpx
import pytest
from core_ai import auth,db,chat,worker


def create(signed,**kwargs):
    r=signed.post('/api/v1/chat/conversations',json={'model':'test:latest',**kwargs})
    assert r.status_code==201,r.text
    return r.json()['id']


def send(signed,ident,**kwargs):
    body={'model':'test:latest','content':'Explain liquidity','request_id':str(uuid.uuid4()),**kwargs}
    r=signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=body)
    assert r.status_code==201,r.text
    return r.json(),body


def test_chat_requires_auth_and_owns_conversations(client,signed):
    ident=create(signed)
    send(signed,ident)
    other=uuid.uuid4()
    db.query('INSERT INTO users(id,username,password_hash) VALUES (%s,%s,%s)',(other,'other-admin',auth.password_hash('other-password-123')))
    token,session=auth.login('other-admin','other-password-123')
    signed.cookies.clear()
    signed.cookies.set(auth.COOKIE,token)
    signed.headers['x-core-ai-csrf']=session['csrf']
    assert signed.get('/api/v1/chat/conversations').json()==[]
    assert signed.get('/api/v1/chat/conversations/'+ident).status_code==404
    assert signed.delete('/api/v1/chat/conversations/'+ident).status_code==404
    assert signed.post('/api/v1/chat/conversations/'+ident+'/stop',json={}).status_code==404
    signed.cookies.clear()
    assert signed.get('/api/v1/chat/conversations').status_code==401


def test_messages_idempotent_and_single_reply(signed):
    ident=create(signed)
    result,body=send(signed,ident,attachments=[{'name':'notes.md','content':'A local reference'}])
    again=signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=body)
    assert again.status_code==201 and again.json()==result
    assert len(signed.get('/api/v1/chat/conversations/'+ident).json()['messages'])==2
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',json={**body,'content':'different'}).status_code==409
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',json={**body,'request_id':str(uuid.uuid4())}).status_code==409


def test_reply_snapshot_is_owner_scoped_and_tracks_state(signed):
    ident=create(signed)
    queued,_=send(signed,ident)
    path=f'/api/v1/chat/conversations/{ident}/reply/{queued["id"]}'
    assert signed.get(path).json()['status']=='QUEUED'
    assert signed.get('/api/v1/chat/statuses',params=[('ids',ident)]).json()==[{'id':ident,'status':'QUEUED'}]

    row=chat.claim()
    chat.persist(row,'Partial answer')
    assert signed.get(path).json()['content']=='Partial answer'
    chat.finish(row,'SUCCEEDED','Final answer')
    final=signed.get(path).json()
    assert final['status']=='SUCCEEDED' and final['message_status']=='COMPLETE'

    other=uuid.uuid4()
    db.query('INSERT INTO users(id,username,password_hash) VALUES (%s,%s,%s)',
             (other,'other-member',auth.password_hash('other-password-123')))
    token,_=auth.login('other-member','other-password-123')
    signed.cookies.clear()
    signed.cookies.set(auth.COOKIE,token)
    assert signed.get(path).status_code==404
    assert signed.get('/api/v1/chat/statuses',params=[('ids',ident)]).json()==[]


def test_history_filters_and_eight_attachment_limit(signed,work):
    active=create(signed,title='Shared phrase',project_id=work['project_id'])
    archived=create(signed,title='Shared phrase archived')
    assert signed.patch('/api/v1/chat/conversations/'+archived,json={'archived':True}).status_code==200
    def matches(**params):
        return {row['id'] for row in signed.get('/api/v1/chat/conversations',params=params).json()}
    assert matches(q='Shared phrase',all_statuses=True)=={active,archived}
    assert matches(q='Shared phrase',archived=True)=={archived}
    assert matches(q='Shared phrase',all_statuses=True,project_id=work['project_id'])=={active}
    attachments=[{'name':f'{i}.txt','content':'notes'} for i in range(8)]
    send(signed,active,attachments=attachments)
    body={'model':'test:latest','content':'Too many attachments','request_id':str(uuid.uuid4()),
          'attachments':attachments,'file_ids':[str(uuid.uuid4())]}
    assert signed.post('/api/v1/chat/conversations/'+active+'/messages',json=body).status_code==422


def test_chat_stream_persists_and_uses_conversation_context(signed,monkeypatch):
    ident=create(signed,mode='professional',instructions='Use concise answers.')
    result,_=send(signed,ident,mode='professional',instructions='Use concise answers.',attachments=[{'name':'notes.md','content':'Untrusted attachment'}])
    row=chat.claim()
    assert row and worker.claim() is None
    real_client=httpx.Client
    def handler(request):
        body=json.loads(request.content)
        assert 'professional work' in body['messages'][0]['content']
        assert 'Untrusted attachment' in body['messages'][-1]['content']
        assert body['messages'][-1]['role']=='user'
        return httpx.Response(200,text='\n'.join(json.dumps(v) for v in [
            {'message':{'content':'First '}}, {'message':{'content':'answer'},'done':True}])+'\n')
    monkeypatch.setattr(chat.httpx,'Client',lambda **_:real_client(transport=httpx.MockTransport(handler)))
    chat.execute(row,threading.Event())
    conversation=signed.get('/api/v1/chat/conversations/'+ident).json()
    assert conversation['messages'][-1]['content']=='First answer'
    assert conversation['messages'][-1]['status']=='COMPLETE'
    assert conversation['generation'] is None
    send(signed,ident,content='What about the previous answer?')
    following=chat.claim()
    history=chat.context(following)
    assert any(m['role']=='assistant' and m['content']=='First answer' for m in history)


@pytest.mark.parametrize(('mode','guidance'), [
    ('quick','direct answer'), ('deep','trade-offs'),
    ('research','available sources'), ('coding','edge cases'),
])
def test_modes_and_models_are_independent(signed, mode, guidance):
    first=create(signed, model='analyst:local', mode=mode)
    second=create(signed, model='editor:local', mode='professional')
    send(signed, first, model='analyst:local', mode=mode, content='First pane prompt')
    send(signed, second, model='editor:local', mode='professional', content='Second pane prompt')

    row=chat.claim()
    assert row['model']=='analyst:local'
    messages=chat.context(row)
    assert guidance in messages[0]['content']
    assert [message['content'] for message in messages[1:]]==['First pane prompt']
    assert chat.claim() is None
    chat.finish(row,'SUCCEEDED','First pane answer')

    row=chat.claim()
    assert row['model']=='editor:local'
    messages=chat.context(row)
    assert [message['content'] for message in messages[1:]]==['Second pane prompt']
    assert signed.get('/api/v1/chat/conversations/'+first).json()['mode']==mode
    assert signed.get('/api/v1/chat/conversations/'+second).json()['mode']=='professional'


def test_stop_cannot_be_overwritten_by_late_reply(signed):
    ident=create(signed)
    send(signed,ident)
    row=chat.claim()
    chat.persist(row,'Partial answer')
    assert signed.post('/api/v1/chat/conversations/'+ident+'/stop',json={}).json()['status']=='CANCEL_REQUESTED'
    chat.finish(row,'SUCCEEDED','Partial answer')
    conversation=signed.get('/api/v1/chat/conversations/'+ident).json()
    assert conversation['messages'][-1]['status']=='CANCELLED'
    assert conversation['messages'][-1]['content']=='Partial answer'
    assert conversation['generation'] is None


def test_stop_queued_reply_archive_search_restore_delete(signed):
    ident=create(signed)
    send(signed,ident,content='Specific research phrase')
    assert signed.post('/api/v1/chat/conversations/'+ident+'/stop',json={}).json()['status']=='CANCELLED'
    assert signed.patch('/api/v1/chat/conversations/'+ident,json={'title':'Research','pinned':True,'archived':True}).status_code==200
    assert signed.get('/api/v1/chat/conversations').json()==[]
    assert signed.get('/api/v1/chat/conversations?archived=true&q=research').json()[0]['id']==ident
    assert signed.patch('/api/v1/chat/conversations/'+ident,json={'archived':False}).status_code==200
    assert signed.delete('/api/v1/chat/conversations/'+ident).status_code==200
    assert not db.query('SELECT id FROM chat_messages WHERE conversation_id=%s',(ident,))


def test_edit_and_retry_create_idempotent_branch_preserving_original(signed):
    ident=create(signed)
    send(signed,ident,content='Original question')
    row=chat.claim()
    chat.finish(row,'SUCCEEDED','Original answer')
    original=signed.get('/api/v1/chat/conversations/'+ident).json()
    body={'model':'test:latest','content':'Edited question','message_id':original['messages'][0]['id'],'request_id':str(uuid.uuid4())}
    fork=signed.post('/api/v1/chat/conversations/'+ident+'/fork',json=body)
    assert fork.status_code==201,fork.text
    target=fork.json()['conversation_id']
    repeat=signed.post('/api/v1/chat/conversations/'+ident+'/fork',json=body)
    assert repeat.status_code==201 and repeat.json()==fork.json()
    assert len(db.query('SELECT id FROM conversations'))==2
    assert signed.get('/api/v1/chat/conversations/'+ident).json()['messages']==original['messages']
    branched=signed.get('/api/v1/chat/conversations/'+target).json()
    assert branched['messages'][0]['content']=='Edited question'
    assert branched['forked_from']==ident


def test_expired_reply_preserves_partial_text_and_can_retry(signed):
    ident=create(signed)
    send(signed,ident)
    row=chat.claim()
    chat.persist(row,'Work before interruption')
    db.query("UPDATE chat_generations SET lease_until=now()-interval '1 minute' WHERE id=%s",(row['id'],))
    chat.recover()
    reply=signed.get('/api/v1/chat/conversations/'+ident).json()['messages'][-1]
    assert reply['status']=='FAILED' and reply['content']=='Work before interruption'
    send(signed,ident,content='Try another question')


def test_chat_and_tasks_share_fifo_slot(signed,work):
    signed.post('/api/v1/runs',json=work)
    ident=create(signed)
    send(signed,ident)
    kind,task=worker.claim_work()
    assert kind=='task' and task
    assert chat.claim() is None
    worker.finish(task['id'],'SUCCEEDED','Task answer')
    kind,reply=worker.claim_work()
    assert kind=='chat' and reply
    assert worker.claim() is None


def test_inputs_bounded_and_mutation_protected(signed):
    ident=create(signed)
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',headers={'x-core-ai-csrf':'wrong'},json={'model':'test:latest','content':'hello','request_id':str(uuid.uuid4())}).status_code==403
    bad={'model':'test:latest','content':'hello','request_id':str(uuid.uuid4()),'attachments':[{'name':'binary','content':'bad\0file'}]}
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=bad).status_code==422
    bad['attachments']=[{'name':'one','content':'a'*20000},{'name':'two','content':'b'*20000}]
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=bad).status_code==422
