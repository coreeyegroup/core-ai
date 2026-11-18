from core_ai import auth,db,models
import pytest

def test_anonymous_data_and_mutations_rejected(client):
    for path in ('projects','agents','runs','documents','events','models','tools','integrations','artifacts','overview'):
        assert client.get('/api/v1/'+path).status_code==401
    assert client.post('/api/v1/projects',json={'name':'blocked'}).status_code==401
    assert client.get('/api/workstation').json()['independent'] is True

def test_origin_csrf_and_revocation(signed):
    assert signed.post('/api/v1/projects',headers={'Origin':'https://wrong.example'},json={'name':'blocked'}).status_code==403
    assert signed.post('/api/v1/projects',headers={'x-core-ai-csrf':'wrong'},json={'name':'blocked'}).status_code==403
    assert signed.delete('/api/v1/session').status_code==200
    assert signed.get('/api/v1/projects').status_code==401

def test_login_requires_origin_and_lockout(client):
    payload={'username':'administrator','password':'wrong'}
    assert client.post('/api/v1/session',json=payload).status_code==403
    for _ in range(5):
        assert client.post('/api/v1/session',headers={'Origin':'http://testserver'},json=payload).status_code==401
    payload['password']='correct-password-123'
    assert client.post('/api/v1/session',headers={'Origin':'http://testserver'},json=payload).status_code==401
    assert db.query('SELECT failed_attempts FROM users',one=True)['failed_attempts']==5

def test_passwords_salted_and_endpoint_constraints():
    a=auth.password_hash('correct-password-123')
    b=auth.password_hash('correct-password-123')
    assert a!=b and auth.password_ok('correct-password-123',a)
    assert not auth.password_ok('wrong',a)
    for endpoint in ('https://api.example.com','http://8.8.8.8:80','http://localhost:11434','http://10.0.0.1/path','http://user:pass@10.0.0.1','http://169.254.169.254'):
        with pytest.raises(ValueError):models.validate_endpoint(endpoint)
    assert models.validate_endpoint('http://10.203.0.2:11434')=='http://10.203.0.2:11434'

def test_seed_does_not_reset_existing_password():
    assert auth.seed('other','different-password-123') is False
    assert db.query('SELECT count(*) AS n FROM users',one=True)['n']==1
