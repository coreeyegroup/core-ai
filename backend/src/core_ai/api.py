"""Versioned CORE-AI API; this product does not depend on any other CORE product."""
import os
import uuid
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from . import __version__, auth, db, models

@asynccontextmanager
async def lifespan(app):
    db.query('SELECT 1')  # schema is migrated by deployment, never through public requests
    yield

app = FastAPI(title='CORE-AI', version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
User = Annotated[dict, Depends(auth.session)]

@app.middleware('http')
async def private_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.exception_handler(Exception)
async def internal_error(request, exc):
    # Never return database URLs, credentials, provider payloads or stack traces.
    import logging
    logging.getLogger('core_ai').error('Request failed: %s', type(exc).__name__)
    return JSONResponse({'detail': 'Operation failed. Check CORE-AI service health.'}, status_code=500)

@app.get('/api/workstation')
def identity():
    try:
        db.query('SELECT 1')
        healthy = True
    except Exception:
        healthy = False
    return {'project_id': 'core-ai', 'contract_version': 1, 'release': __version__,
            'database_connected': healthy, 'independent': True}

@app.get('/health')
def health(response: Response):
    result = identity()
    if not result['database_connected']:
        response.status_code = 503
    return result

class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

@app.post('/api/v1/session')
def sign_in(body: Credentials, request: Request, response: Response):
    auth.origin_check(request)
    token, result = auth.login(body.username.strip().lower(), body.password)
    response.set_cookie(auth.COOKIE, token, httponly=True, secure=os.environ.get('CORE_AI_ORIGIN','').startswith('https:'),
                        samesite='strict', max_age=8*3600, path='/')
    return result

@app.get('/api/v1/session')
def current(user: User):
    return {'username': user['username'], 'csrf': user['csrf']}

@app.delete('/api/v1/session')
def sign_out(request: Request, response: Response, user: User):
    db.query('DELETE FROM sessions WHERE token_hash=%s', (auth.token_hash(request.cookies.get(auth.COOKIE, '')),))
    db.event('session.revoked', user['id'])
    response.delete_cookie(auth.COOKIE, path='/')
    return {'ok': True}

@app.get('/api/v1/overview')
def overview(user: User):
    counts = {}
    for name in ('projects', 'agents', 'documents'):
        counts[name] = db.query(f'SELECT count(*) AS n FROM {name}', one=True)['n']
    return {**counts, 'runs': db.query('SELECT status,count(*) AS n FROM runs GROUP BY status'),
            'worker': db.query("SELECT heartbeat,heartbeat>now()-interval '20 seconds' AS online FROM worker_status WHERE id='main'", one=True),
            'inference': models.config(), 'release': __version__}

class Project(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=4000)

@app.get('/api/v1/projects')
def projects(user: User):
    return db.query('SELECT * FROM projects ORDER BY created_at')

@app.post('/api/v1/projects', status_code=201)
def create_project(body: Project, user: User):
    ident = uuid.uuid4()
    with db.connect() as conn:
        conn.execute('INSERT INTO projects(id,name,description) VALUES (%s,%s,%s)', (ident, body.name, body.description))
        db.event('project.created', user['id'], {'id': str(ident), 'name': body.name}, conn=conn)
    return {'id': ident}

class Agent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=16000)
    enabled: bool = True

@app.get('/api/v1/agents')
def agents(user: User):
    return db.query('SELECT * FROM agents ORDER BY created_at')

@app.post('/api/v1/agents', status_code=201)
def create_agent(body: Agent, user: User):
    ident = uuid.uuid4()
    db.query('INSERT INTO agents(id,name,instructions,enabled) VALUES (%s,%s,%s,%s)',
             (ident, body.name, body.instructions, body.enabled))
    db.event('agent.created', user['id'], {'id': str(ident)})
    return {'id': ident}

@app.put('/api/v1/agents/{ident}')
def update_agent(ident: uuid.UUID, body: Agent, user: User):
    row = db.query('UPDATE agents SET name=%s,instructions=%s,enabled=%s,version=version+1 WHERE id=%s RETURNING version',
                   (body.name, body.instructions, body.enabled, ident), one=True)
    if not row:
        raise HTTPException(404, 'Agent not found.')
    db.event('agent.updated', user['id'], {'id': str(ident), **row})
    return row

@app.get('/api/v1/models')
def model_list(user: User):
    try:
        return models.list_models()
    except Exception:
        return {'available': False, 'models': [], 'config': models.config(),
                'error': 'Ollama is unreachable. Check the laptop, WireGuard and Ollama listener.'}

class Inference(BaseModel):
    endpoint: str = Field(max_length=100)
    model: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')

@app.put('/api/v1/models/config')
def inference(body: Inference, user: User):
    try:
        models.configure(body.endpoint, body.model)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.event('inference.configured', user['id'], {'endpoint': body.endpoint, 'model': body.model})
    return {'ok': True}

class Run(BaseModel):
    project_id: uuid.UUID
    agent_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')

@app.get('/api/v1/runs')
def runs(user: User):
    return db.query('''SELECT r.id,r.project_id,p.name AS project,r.agent_id,a.name AS agent,r.model,r.status,
        r.created_at,r.started_at,r.finished_at,left(r.prompt,200) AS prompt
        FROM runs r JOIN projects p ON p.id=r.project_id JOIN agents a ON a.id=r.agent_id
        ORDER BY r.created_at DESC LIMIT 100''')

@app.post('/api/v1/runs', status_code=201)
def submit_run(body: Run, user: User):
    ident = uuid.uuid4()
    with db.connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(187875435)')
        if conn.execute("SELECT (SELECT count(*) FROM runs WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED'))+(SELECT count(*) FROM chat_generations WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS n").fetchone()['n'] >= 20:
            raise HTTPException(409, 'The queue is full. Wait or cancel an existing task.')
        agent = conn.execute('SELECT * FROM agents WHERE id=%s AND enabled', (body.agent_id,)).fetchone()
        if not agent or not conn.execute('SELECT id FROM projects WHERE id=%s', (body.project_id,)).fetchone():
            raise HTTPException(422, 'Choose an existing project and enabled agent.')
        conn.execute('''INSERT INTO runs(id,project_id,agent_id,agent_version,instructions,prompt,model,status,requested_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s)''',
            (ident,body.project_id,body.agent_id,agent['version'],agent['instructions'],body.prompt,body.model,user['id']))
        db.event('run.queued', user['id'], {'agent_version': agent['version']}, ident, conn)
    return {'id': ident}

@app.get('/api/v1/runs/{ident}')
def run_detail(ident: uuid.UUID, user: User):
    row = db.query('SELECT * FROM runs WHERE id=%s', (ident,), one=True)
    if not row:
        raise HTTPException(404, 'Task not found.')
    row['events'] = db.query('SELECT * FROM events WHERE run_id=%s ORDER BY id', (ident,))
    return row

@app.post('/api/v1/runs/{ident}/cancel')
def cancel(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        row = conn.execute("""UPDATE runs SET status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,
            finished_at=CASE WHEN status='QUEUED' THEN now() ELSE finished_at END
            WHERE id=%s AND status IN ('QUEUED','RUNNING') RETURNING status""", (ident,)).fetchone()
        if not row:
            raise HTTPException(409, 'Task is terminal or cancellation was already requested.')
        db.event('run.cancel_requested', user['id'], run_id=ident, conn=conn)
    return row

class Document(BaseModel):
    project_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)

@app.get('/api/v1/documents')
def documents(user: User, project_id: uuid.UUID | None = None):
    if project_id:
        return db.query('SELECT * FROM documents WHERE project_id=%s ORDER BY created_at DESC', (project_id,))
    return db.query('SELECT id,project_id,title,created_at FROM documents ORDER BY created_at DESC LIMIT 200')

@app.post('/api/v1/documents', status_code=201)
def add_document(body: Document, user: User):
    if not db.query('SELECT id FROM projects WHERE id=%s', (body.project_id,), one=True):
        raise HTTPException(422, 'Project not found.')
    ident = uuid.uuid4()
    db.query('INSERT INTO documents(id,project_id,title,content) VALUES (%s,%s,%s,%s)',
             (ident,body.project_id,body.title,body.content))
    db.event('document.created', user['id'], {'id': str(ident)})
    return {'id': ident}

@app.delete('/api/v1/documents/{ident}')
def remove_document(ident: uuid.UUID, user: User):
    if not db.query('DELETE FROM documents WHERE id=%s RETURNING id', (ident,), one=True):
        raise HTTPException(404, 'Document not found.')
    db.event('document.deleted', user['id'], {'id': str(ident)})
    return {'ok': True}

@app.get('/api/v1/events')
def events(user: User):
    return db.query('SELECT * FROM events ORDER BY id DESC LIMIT 200')

@app.get('/api/v1/artifacts')
def artifacts(user: User):
    return db.query("SELECT id,project_id,model,output,finished_at FROM runs WHERE status='SUCCEEDED' ORDER BY finished_at DESC LIMIT 100")

@app.get('/api/v1/tools')
def tools(user: User):
    return [{'id':'knowledge.search', 'mode':'read', 'enabled':True, 'description':'Search task-project documents and record source IDs before inference.'},
            {'id':'model.generate', 'mode':'inference', 'enabled':True, 'description':'Generate a bounded answer with the selected local Ollama model.'}]

@app.get('/api/v1/integrations')
def integrations(user: User):
    return {'connected': [], 'policy':'Optional versioned API connectors. No other product is required or configured.'}

# Chat is an independent product module, sharing only local identity and inference.
from .chat import router as chat_router
app.include_router(chat_router)
