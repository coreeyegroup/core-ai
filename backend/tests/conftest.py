import os
import pytest
from fastapi.testclient import TestClient
from core_ai import auth, db
from core_ai.api import app

@pytest.fixture(autouse=True)
def database():
    if not os.environ.get('CORE_AI_DATABASE_URL'):
        pytest.skip('CORE_AI_DATABASE_URL is required for real PostgreSQL integration tests.')
    os.environ['CORE_AI_ORIGIN']='http://testserver'
    from pathlib import Path
    db.migrate(Path(__file__).resolve().parents[1]/'sql')
    db.query('TRUNCATE chat_generations,chat_messages,conversations,events,sessions,runs,documents,agents,projects,users,worker_status,settings RESTART IDENTITY CASCADE')
    auth.seed('administrator','correct-password-123')
    yield

@pytest.fixture
def client():
    with TestClient(app,raise_server_exceptions=False) as c:
        yield c

@pytest.fixture
def signed(client):
    r=client.post('/api/v1/session',headers={'Origin':'http://testserver'},json={'username':'administrator','password':'correct-password-123'})
    assert r.status_code==200,r.text
    client.headers.update({'Origin':'http://testserver','x-core-ai-csrf':r.json()['csrf']})
    return client

@pytest.fixture
def work(signed):
    project=signed.post('/api/v1/projects',json={'name':'Research','description':'Project one'}).json()['id']
    agent=signed.post('/api/v1/agents',json={'name':'Analyst','instructions':'Answer with sources.'}).json()['id']
    return {'project_id':project,'agent_id':agent,'prompt':'liquidity','model':'test:latest'}
