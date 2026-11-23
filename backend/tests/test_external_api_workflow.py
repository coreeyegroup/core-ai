import base64

from core_ai import db, external_connections as external


def test_fetch_snapshot_and_confirm_write(signed, work, monkeypatch):
    monkeypatch.setenv(external.key_storage.ENV_KEY, base64.b64encode(b'test key material' * 16).decode())
    calls = []

    def transport(url, method, headers, credential, body, *, probe=False):
        calls.append((url.host, method, probe))
        if method == 'HEAD':
            return 204, None
        return 200, {'price': 1.25}

    monkeypatch.setattr(external, 'send', transport)
    base = '/api/v1/external-connections'
    settings = {'name':'Forex feed','provider':'twelvedata','endpoint':'https://api.twelvedata.com/quote?symbol=EUR%2FUSD',
                'method':'GET','auth':'apikey','secret':'fixture-credential'}
    created = signed.post(base, json=settings)
    assert created.status_code == 201, created.text
    ident = created.json()['id']
    listed = signed.get(base).json()[0]
    assert listed['has_secret']
    assert 'secret' not in listed and 'fixture-credential' not in str(listed)
    snapshot = signed.post(f'{base}/{ident}/run', json={'project_id':work['project_id']})
    assert snapshot.status_code == 200, snapshot.text
    source = snapshot.json()['source_id']
    assert source
    doc = next(item for item in signed.get('/api/v1/documents', params={'project_id':work['project_id']}).json()
               if str(item['id']) == source)
    assert '1.25' in doc['content']
    edited = {**settings, 'endpoint':'https://api.twelvedata.com/quote?symbol=GBP%2FUSD','version':1}
    edited.pop('secret')
    assert signed.put(f'{base}/{ident}', json=edited).status_code == 200
    assert signed.put(f'{base}/{ident}', json=edited).status_code == 409

    webhook = signed.post(base, json={'name':'Workflow','provider':'n8n','endpoint':'https://n8n.example.com/webhook/review',
                          'method':'POST','auth':'header','header_name':'X-Hook-Key','secret':'fixture-hook'})
    assert webhook.status_code == 201, webhook.text
    outbound = webhook.json()['id']
    assert signed.post(f'{base}/{outbound}/run', json={'body':{'task':'review'}}).status_code == 422
    assert signed.post(f'{base}/{outbound}/test', json={}).json()['method'] == 'HEAD'
    db.query("UPDATE external_api_connections SET last_started_at=NULL WHERE id=%s", (outbound,))
    assert signed.post(f'{base}/{outbound}/run', json={'confirmed':True,'body':{'task':'review'}}).json()['outcome'] == 'ok'
    assert calls == [('api.twelvedata.com','GET',False),('n8n.example.com','HEAD',True),('n8n.example.com','POST',False)]
    assert 'fixture-hook' not in signed.get(f'{base}/{outbound}/activity').text
