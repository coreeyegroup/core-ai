"""Versioned CORE-AI API; this product does not depend on any other CORE product."""
import os
import uuid

import httpx
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from . import __version__, auth, db, models, access, runs as run_queue, research as research_workflow, agent_runtime, program_gateway, capability_policy, execution_policy

@asynccontextmanager
async def lifespan(app):
    db.query('SELECT 1')  # schema is migrated by deployment, never through public requests
    yield

app = FastAPI(title='CORE-AI', version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
User = Annotated[dict, Depends(auth.session)]

@app.middleware('http')
async def private_headers(request, call_next):
    if request.url.path in ('/api/v1/programs/run','/api/v1/programs/jobs') and request.method=='POST':
        try:auth.session(request)
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
        length=request.headers.get('content-length','')
        if not length.isascii() or not length.isdigit() or len(length)>7 or int(length)>6*1024*1024:
            return JSONResponse({'detail':'Program requests require a body of at most 6 MiB.'},status_code=413)
    if request.url.path=='/api/v1/files' and request.method=='POST':
        # Authenticate before parsing a potentially large multipart body.
        try:auth.session(request)
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
        length=request.headers.get('content-length','0')
        if not length.isdigit() or int(length)>11*1024*1024:
            return JSONResponse({'detail':'Upload exceeds the 10 MB file limit.'},status_code=413)
    if request.url.path.startswith('/api/v1/external-connections') and request.method in ('POST','PUT'):
        length = request.headers.get('content-length','')
        if not length.isascii() or not length.isdigit() or len(length)>6 or int(length)>80*1024:
            return JSONResponse({'detail':'External connection requests require a body of at most 80 KB.'},status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    detail = [{key: error[key] for key in ('loc','msg','type')} for error in exc.errors()]
    return JSONResponse({'detail':detail}, status_code=422)


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

@app.get('/api/v1/readiness')
def readiness(response: Response, user: User):
    access.admin(user)
    worker = db.query("""SELECT heartbeat>now()-interval '20 seconds' AS online
        FROM worker_status WHERE id='main'""", one=True)
    try:
        with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
            client.get(models.config()['endpoint'] + '/api/tags').raise_for_status()
        provider_online = True
    except httpx.HTTPError:
        provider_online = False
    worker_online = bool(worker and worker['online'])
    ready = worker_online and provider_online
    if not ready:
        response.status_code = 503
    return {'ready': ready, 'database_connected': True, 'worker_online': worker_online,
            'provider_online': provider_online}


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
    return {'username': user['username'], 'csrf': user['csrf'], 'role':user['role'],'id':str(user['id'])}

@app.delete('/api/v1/session')
def sign_out(request: Request, response: Response, user: User):
    db.query('DELETE FROM sessions WHERE token_hash=%s', (auth.token_hash(request.cookies.get(auth.COOKIE, '')),))
    db.event('session.revoked', user['id'])
    response.delete_cookie(auth.COOKIE, path='/')
    return {'ok': True}

@app.get('/api/v1/overview')
def overview(user: User):
    project_ids=[p['id'] for p in access.allowed_projects(user)]
    counts={'projects':len(project_ids),'agents':db.query("SELECT count(*) AS n FROM agents WHERE owner_id=%s OR %s='ADMIN'",(user['id'],user['role']),one=True)['n'],
            'documents':db.query('SELECT count(*) AS n FROM documents WHERE project_id=ANY(%s)',(project_ids,),one=True)['n']}
    cfg=models.config()
    if user['role']!='ADMIN':cfg={**cfg,'endpoint':'Private local provider'}
    return {**counts,'runs':db.query('SELECT status,count(*) AS n FROM runs WHERE project_id=ANY(%s) GROUP BY status',(project_ids,)),
            'worker':db.query("SELECT heartbeat,heartbeat>now()-interval '20 seconds' AS online FROM worker_status WHERE id='main'",one=True),
            'inference':cfg,'release':__version__,'role':user['role']}

class Project(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=4000)
    instructions: str = Field(default='',max_length=8000)

@app.get('/api/v1/projects')
def projects(user: User, deleted: bool = False):
    if deleted:
        access.writer(user)
    return access.allowed_projects(user, deleted)

@app.post('/api/v1/projects', status_code=201)
def create_project(body: Project, user: User):
    ident = uuid.uuid4()
    with db.connect() as conn:
        conn.execute('INSERT INTO projects(id,name,description,owner_id,instructions) VALUES (%s,%s,%s,%s,%s)', (ident, body.name, body.description,user['id'],body.instructions))
        conn.execute("INSERT INTO project_members VALUES (%s,%s,'OWNER')",(ident,user['id']))
        db.event('project.created', user['id'], {'id': str(ident), 'name': body.name}, conn=conn)
    return {'id': ident}

class Agent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1, max_length=16000)
    enabled: bool = True
    runtime_mode: str = Field(default='analysis',pattern=r'^(analysis|tools)$')
    tools: list[str] = Field(default_factory=lambda:['knowledge.search','project.inspect'],max_length=5)
    program_scope: list[str] | None = Field(default=None,max_length=200)

@app.get('/api/v1/agents')
def agents(user: User, include_deleted: bool = False):
    return db.query("""SELECT * FROM agents
        WHERE (owner_id=%s OR %s='ADMIN') AND (%s OR deleted_at IS NULL) ORDER BY created_at""",
        (user['id'],user['role'],include_deleted))

@app.post('/api/v1/agents', status_code=201)
def create_agent(body: Agent, user: User):
    access.writer(user)
    ident = uuid.uuid4()
    from psycopg.types.json import Jsonb
    if any(t not in agent_runtime.SCHEMAS for t in body.tools):raise HTTPException(422,'Unsupported agent tool.')
    scope=capability_policy.validate_scope(body.program_scope) or []
    db.query('INSERT INTO agents(id,name,instructions,enabled,owner_id,runtime_mode,tools,program_scope) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
             (ident, body.name, body.instructions, body.enabled,user['id'],body.runtime_mode,Jsonb(body.tools),Jsonb(scope)))
    db.event('agent.created', user['id'], {'id': str(ident)})
    return {'id': ident}

@app.put('/api/v1/agents/{ident}')
def update_agent(ident: uuid.UUID, body: Agent, user: User):
    from psycopg.types.json import Jsonb
    access.writer(user)
    with db.connect() as conn:access.agent(conn,user,ident)
    if any(t not in agent_runtime.SCHEMAS for t in body.tools):raise HTTPException(422,'Unsupported agent tool.')
    scope=capability_policy.validate_scope(body.program_scope)
    row = db.query('UPDATE agents SET name=%s,instructions=%s,enabled=%s,runtime_mode=%s,tools=%s,program_scope=coalesce(%s,program_scope),version=version+1 WHERE id=%s AND deleted_at IS NULL RETURNING version',
                   (body.name, body.instructions, body.enabled,body.runtime_mode,Jsonb(body.tools),Jsonb(scope) if scope is not None else None,ident), one=True)
    if not row:
        raise HTTPException(404, 'Agent not found.')
    db.event('agent.updated', user['id'], {'id': str(ident), **row})
    return row

@app.delete('/api/v1/agents/{ident}')
def delete_agent(ident: uuid.UUID, user: User):
    return set_agent_deleted(ident, user, True)


@app.post('/api/v1/agents/{ident}/restore')
def restore_agent(ident: uuid.UUID, user: User):
    return set_agent_deleted(ident, user, False)


def set_agent_deleted(ident, user, deleted):
    access.writer(user)
    with db.connect() as conn:
        access.agent(conn, user, ident)
        conn.execute("""UPDATE agents SET deleted_at=CASE WHEN %s THEN COALESCE(deleted_at,now()) END,
            enabled=false,version=version+1 WHERE id=%s AND (deleted_at IS NULL)=%s""", (deleted,ident,deleted))
        db.event('agent.deleted' if deleted else 'agent.restored', user['id'], {'id':str(ident)}, conn=conn)
    return {'ok': True}


@app.get('/api/v1/models')
def model_list(user: User, catalog: bool = False):
    try:
        result=models.list_models()
        if catalog:result=models.with_capabilities(result)
        if user['role']!='ADMIN':result['config']={**result['config'],'endpoint':'Private local provider'}
        return result
    except Exception:
        return {'available': False, 'models': [], 'config':models.config() if user['role']=='ADMIN' else {'model':models.config()['model'],'endpoint':'Private local provider'},
                'error': 'Ollama is unreachable. Check the laptop, WireGuard and Ollama listener.'}

class Inference(BaseModel):
    endpoint: str = Field(max_length=100)
    model: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')

@app.put('/api/v1/models/config')
def inference(body: Inference, user: User):
    access.admin(user)
    try:
        models.configure(body.endpoint, body.model)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.event('inference.configured', user['id'], {'endpoint': body.endpoint, 'model': body.model})
    return {'ok': True}

class Run(BaseModel):
    research: research_workflow.Specification | None = None
    project_id: uuid.UUID
    agent_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+
def runs(user: User):
    return db.query('''SELECT r.id,r.project_id,p.name AS project,r.agent_id,a.name AS agent,r.model,r.status,
        r.created_at,r.started_at,r.finished_at,left(r.prompt,200) AS prompt,w.phase AS research_phase
        FROM runs r JOIN projects p ON p.id=r.project_id JOIN agents a ON a.id=r.agent_id
        LEFT JOIN research_workflows w ON w.run_id=r.id
        WHERE p.deleted_at IS NULL AND (%s='ADMIN' OR (EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=r.project_id AND m.user_id=%s)
                             AND (w.run_id IS NULL OR r.requested_by=%s)))
        ORDER BY r.created_at DESC LIMIT 100''',(user['role'],user['id'],user['id']))

@app.post('/api/v1/runs', status_code=201)
def submit_run(body: Run, user: User):
    with db.connect() as conn:
        access.project(conn,user,body.project_id,True)
        agent = access.agent(conn,user,body.agent_id)
        if not agent['enabled']:
            raise HTTPException(422, 'Choose an existing project and enabled agent.')
        ident = run_queue.enqueue(conn, project_id=body.project_id, agent=agent, prompt=body.prompt,
                                  model=body.model, user_id=user['id'], timeout_seconds=body.timeout_seconds or execution_policy.get().task_seconds,
                                  max_output_tokens=body.max_output_tokens,context_tokens=body.context_tokens,scheduled=bool(body.research and body.research.scheduled_for))
        if body.research:
            if not body.prompt.strip() or '\x00' in body.prompt:
                raise HTTPException(422,'Enter a nonempty research goal.')
            research_workflow.create(conn, ident, body.research)
    return {'id': ident}

@app.get('/api/v1/runs/{ident}')
def run_detail(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM runs WHERE id=%s', (ident,)).fetchone()
        if not row or row['project_id'] is None or row['agent_id'] is None:
            raise HTTPException(404, 'Task not found.')
        access.project(conn,user,row['project_id'])
        row.pop('claim_token', None)
        row['research'] = conn.execute("SELECT * FROM research_workflows WHERE run_id=%s", (ident,)).fetchone()
        if row['research'] and row['requested_by'] != user['id'] and user['role'] != 'ADMIN':
            raise HTTPException(404, 'Task not found.')
        row['steps'] = conn.execute('SELECT * FROM agent_steps WHERE run_id=%s ORDER BY id',(ident,)).fetchall()
        row['events'] = conn.execute('SELECT * FROM events WHERE run_id=%s ORDER BY id',(ident,)).fetchall()
    return row


@app.post('/api/v1/runs/{ident}/pause')
def pause_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.control(conn, ident, user, 'pause')


@app.post('/api/v1/runs/{ident}/resume')
def resume_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.control(conn, ident, user, 'resume')


@app.post('/api/v1/runs/{ident}/retry', status_code=201)
def retry_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.retry(conn, ident, user)


@app.post('/api/v1/runs/{ident}/review')
def review_research(ident: uuid.UUID, body: research_workflow.Review, user: User):
    with db.connect() as conn:
        return research_workflow.review(conn, ident, user, body)


@app.post('/api/v1/runs/{ident}/cancel')
def cancel(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        task=conn.execute('SELECT project_id,agent_id FROM runs WHERE id=%s',(ident,)).fetchone()
        if not task or task['project_id'] is None or task['agent_id'] is None:raise HTTPException(404,'Task not found.')
        access.project(conn,user,task['project_id'],True)
        if conn.execute('SELECT run_id FROM research_workflows WHERE run_id=%s', (ident,)).fetchone():
            research_workflow.authorize(conn, ident, user, True)
        row = conn.execute("""UPDATE runs SET status=CASE WHEN status='RUNNING' THEN 'CANCEL_REQUESTED' ELSE 'CANCELLED' END,
            finished_at=CASE WHEN status='RUNNING' THEN finished_at ELSE now() END
            WHERE id=%s AND status IN ('QUEUED','RUNNING','PAUSED','WAITING_REVIEW','SCHEDULED') RETURNING status""", (ident,)).fetchone()
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
        with db.connect() as conn:access.project(conn,user,project_id)
        return db.query('SELECT * FROM documents WHERE project_id=%s ORDER BY created_at DESC', (project_id,))
    return db.query("SELECT d.id,d.project_id,d.title,d.version,d.enabled,d.created_at FROM documents d JOIN projects p ON p.id=d.project_id WHERE p.deleted_at IS NULL AND (%s='ADMIN' OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=d.project_id AND m.user_id=%s)) ORDER BY created_at DESC LIMIT 200",(user['role'],user['id']))

@app.post('/api/v1/documents', status_code=201)
def add_document(body: Document, user: User):
    ident = uuid.uuid4()
    with db.connect() as conn:
        access.project(conn, user, body.project_id, True)
        conn.execute('INSERT INTO documents(id,project_id,title,content) VALUES (%s,%s,%s,%s)',
                     (ident, body.project_id, body.title, body.content))
        conn.execute('INSERT INTO document_versions(document_id,project_id,version,title,content) VALUES (%s,%s,1,%s,%s)',
                     (ident, body.project_id, body.title, body.content))
        db.event('document.created', user['id'], {'id': str(ident)}, conn=conn)
    return {'id': ident}

@app.delete('/api/v1/documents/{ident}')
def remove_document(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        source=conn.execute('SELECT project_id FROM documents WHERE id=%s',(ident,)).fetchone()
        if not source:raise HTTPException(404,'Document not found.')
        access.project(conn,user,source['project_id'],True)
        conn.execute('DELETE FROM document_versions WHERE document_id=%s',(ident,))
        conn.execute('DELETE FROM documents WHERE id=%s',(ident,))
        db.event('document.deleted', user['id'], {'id': str(ident)}, conn=conn)
    return {'ok': True}

@app.get('/api/v1/events')
def events(user: User):
    return db.query("SELECT * FROM events WHERE %s='ADMIN' OR actor=%s ORDER BY id DESC LIMIT 200",(user['role'],str(user['id'])))

@app.get('/api/v1/artifacts')
def artifacts(user: User):
    return db.query("SELECT id,project_id,model,output,finished_at FROM runs r WHERE status='SUCCEEDED' AND NOT EXISTS (SELECT 1 FROM research_workflows w WHERE w.run_id=r.id) AND r.project_id IS NOT NULL AND r.agent_id IS NOT NULL AND (%s='ADMIN' OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=r.project_id AND m.user_id=%s)) ORDER BY finished_at DESC LIMIT 100",(user['role'],user['id']))

@app.get('/api/v1/tools')
def tools(user: User):
    return [{'id':'knowledge.search','mode':'read','enabled':True,'description':'Search only the authorized task project and return source excerpts.'},
            {'id':'project.inspect','mode':'read','enabled':True,'description':'Inspect the authorized project and its source inventory.'},
            {'id':'artifact.create','mode':'write','enabled':user['role']!='VIEWER','description':'Create a private, versioned artifact from a permitted agent task.'},
            {'id':'model.generate','mode':'inference','enabled':True,'description':'Use the selected local model. Tools mode requires verified model tool support.'},
            {'id':'program.list','mode':'read','enabled':True,'description':'Discover qualified independent programs when the private gateway is online.'},
            {'id':'program.run','mode':'execute','enabled':user['role']!='VIEWER','description':'Invoke only qualified offline program recipes; requires explicit agent tool permission.'}]

@app.get('/api/v1/integrations')
def integrations(user: User):
    connected = []
    if user['role'] == 'ADMIN':
        connected = db.query("""
            SELECT c.id,c.name,c.client_type,c.model_access,c.webhook_destination IS NOT NULL AS has_webhook
            FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.revoked_at IS NULL AND NOT c.paused
              AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN'
            ORDER BY c.created_at DESC LIMIT 200
        """)
    return {'connected': connected, 'policy':'Optional versioned API connections. No other product is required.'}

# Chat is an independent product module, sharing only local identity and inference.
from .chat import router as chat_router
app.include_router(chat_router)

from .skills import router as skills_router
app.include_router(skills_router)
from .repository_intelligence import router as repository_intelligence_router
app.include_router(repository_intelligence_router)

from .connections import router as connections_router
app.include_router(connections_router)

from .workspace import router as workspace_router
from .files import router as files_router
app.include_router(workspace_router)
app.include_router(files_router)

@app.get('/api/v1/models/inspect')
def inspect_model(model:str,user:User):
    try:return models.inspect_model(model)
    except Exception:raise HTTPException(422,'Model inspection failed. Confirm the model is installed and the provider is reachable.')

@app.get('/api/v1/operations/metrics')
def operation_metrics(user:User):
    ids=[p['id'] for p in access.allowed_projects(user)]
    return {'tasks':db.query('SELECT id,status,model,metrics,created_at,finished_at FROM runs WHERE project_id=ANY(%s) ORDER BY created_at DESC LIMIT 100',(ids,)),
            'chats':db.query('SELECT id,status,model,metrics,created_at,finished_at FROM chat_generations WHERE requested_by=%s ORDER BY created_at DESC LIMIT 100',(user['id'],)),
            'files':db.query("SELECT status,count(*) AS n FROM workspace_files WHERE owner_id=%s OR %s='ADMIN' GROUP BY status",(user['id'],user['role']))}

from .external_connections import router as external_connections_router

app.include_router(external_connections_router)

app.include_router(program_gateway.router)
)
    timeout_seconds: int | None = Field(default=None,ge=60,le=3600)
    max_output_tokens: int = Field(default=2048,ge=128,le=4096)
    context_tokens: int = Field(default=8192,ge=1024,le=32768)

@app.get('/api/v1/runs')
def runs(user: User):
    return db.query('''SELECT r.id,r.project_id,p.name AS project,r.agent_id,a.name AS agent,r.model,r.status,
        r.created_at,r.started_at,r.finished_at,left(r.prompt,200) AS prompt,w.phase AS research_phase
        FROM runs r JOIN projects p ON p.id=r.project_id JOIN agents a ON a.id=r.agent_id
        LEFT JOIN research_workflows w ON w.run_id=r.id
        WHERE p.deleted_at IS NULL AND (%s='ADMIN' OR (EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=r.project_id AND m.user_id=%s)
                             AND (w.run_id IS NULL OR r.requested_by=%s)))
        ORDER BY r.created_at DESC LIMIT 100''',(user['role'],user['id'],user['id']))

@app.post('/api/v1/runs', status_code=201)
def submit_run(body: Run, user: User):
    with db.connect() as conn:
        access.project(conn,user,body.project_id,True)
        agent = access.agent(conn,user,body.agent_id)
        if not agent['enabled']:
            raise HTTPException(422, 'Choose an existing project and enabled agent.')
        ident = run_queue.enqueue(conn, project_id=body.project_id, agent=agent, prompt=body.prompt,
                                  model=body.model, user_id=user['id'], scheduled=bool(body.research and body.research.scheduled_for))
        if body.research:
            if not body.prompt.strip() or '\x00' in body.prompt:
                raise HTTPException(422,'Enter a nonempty research goal.')
            research_workflow.create(conn, ident, body.research)
    return {'id': ident}

@app.get('/api/v1/runs/{ident}')
def run_detail(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM runs WHERE id=%s', (ident,)).fetchone()
        if not row or row['project_id'] is None or row['agent_id'] is None:
            raise HTTPException(404, 'Task not found.')
        access.project(conn,user,row['project_id'])
        row.pop('claim_token', None)
        row['research'] = conn.execute("SELECT * FROM research_workflows WHERE run_id=%s", (ident,)).fetchone()
        if row['research'] and row['requested_by'] != user['id'] and user['role'] != 'ADMIN':
            raise HTTPException(404, 'Task not found.')
        row['steps'] = conn.execute('SELECT * FROM agent_steps WHERE run_id=%s ORDER BY id',(ident,)).fetchall()
        row['events'] = conn.execute('SELECT * FROM events WHERE run_id=%s ORDER BY id',(ident,)).fetchall()
    return row


@app.post('/api/v1/runs/{ident}/pause')
def pause_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.control(conn, ident, user, 'pause')


@app.post('/api/v1/runs/{ident}/resume')
def resume_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.control(conn, ident, user, 'resume')


@app.post('/api/v1/runs/{ident}/retry', status_code=201)
def retry_research(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        return research_workflow.retry(conn, ident, user)


@app.post('/api/v1/runs/{ident}/review')
def review_research(ident: uuid.UUID, body: research_workflow.Review, user: User):
    with db.connect() as conn:
        return research_workflow.review(conn, ident, user, body)


@app.post('/api/v1/runs/{ident}/cancel')
def cancel(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        task=conn.execute('SELECT project_id,agent_id FROM runs WHERE id=%s',(ident,)).fetchone()
        if not task or task['project_id'] is None or task['agent_id'] is None:raise HTTPException(404,'Task not found.')
        access.project(conn,user,task['project_id'],True)
        if conn.execute('SELECT run_id FROM research_workflows WHERE run_id=%s', (ident,)).fetchone():
            research_workflow.authorize(conn, ident, user, True)
        row = conn.execute("""UPDATE runs SET status=CASE WHEN status='RUNNING' THEN 'CANCEL_REQUESTED' ELSE 'CANCELLED' END,
            finished_at=CASE WHEN status='RUNNING' THEN finished_at ELSE now() END
            WHERE id=%s AND status IN ('QUEUED','RUNNING','PAUSED','WAITING_REVIEW','SCHEDULED') RETURNING status""", (ident,)).fetchone()
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
        with db.connect() as conn:access.project(conn,user,project_id)
        return db.query('SELECT * FROM documents WHERE project_id=%s ORDER BY created_at DESC', (project_id,))
    return db.query("SELECT d.id,d.project_id,d.title,d.version,d.enabled,d.created_at FROM documents d JOIN projects p ON p.id=d.project_id WHERE p.deleted_at IS NULL AND (%s='ADMIN' OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=d.project_id AND m.user_id=%s)) ORDER BY created_at DESC LIMIT 200",(user['role'],user['id']))

@app.post('/api/v1/documents', status_code=201)
def add_document(body: Document, user: User):
    ident = uuid.uuid4()
    with db.connect() as conn:
        access.project(conn, user, body.project_id, True)
        conn.execute('INSERT INTO documents(id,project_id,title,content) VALUES (%s,%s,%s,%s)',
                     (ident, body.project_id, body.title, body.content))
        conn.execute('INSERT INTO document_versions(document_id,project_id,version,title,content) VALUES (%s,%s,1,%s,%s)',
                     (ident, body.project_id, body.title, body.content))
        db.event('document.created', user['id'], {'id': str(ident)}, conn=conn)
    return {'id': ident}

@app.delete('/api/v1/documents/{ident}')
def remove_document(ident: uuid.UUID, user: User):
    with db.connect() as conn:
        source=conn.execute('SELECT project_id FROM documents WHERE id=%s',(ident,)).fetchone()
        if not source:raise HTTPException(404,'Document not found.')
        access.project(conn,user,source['project_id'],True)
        conn.execute('DELETE FROM document_versions WHERE document_id=%s',(ident,))
        conn.execute('DELETE FROM documents WHERE id=%s',(ident,))
        db.event('document.deleted', user['id'], {'id': str(ident)}, conn=conn)
    return {'ok': True}

@app.get('/api/v1/events')
def events(user: User):
    return db.query("SELECT * FROM events WHERE %s='ADMIN' OR actor=%s ORDER BY id DESC LIMIT 200",(user['role'],str(user['id'])))

@app.get('/api/v1/artifacts')
def artifacts(user: User):
    return db.query("SELECT id,project_id,model,output,finished_at FROM runs r WHERE status='SUCCEEDED' AND NOT EXISTS (SELECT 1 FROM research_workflows w WHERE w.run_id=r.id) AND r.project_id IS NOT NULL AND r.agent_id IS NOT NULL AND (%s='ADMIN' OR EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=r.project_id AND m.user_id=%s)) ORDER BY finished_at DESC LIMIT 100",(user['role'],user['id']))

@app.get('/api/v1/tools')
def tools(user: User):
    return [{'id':'knowledge.search','mode':'read','enabled':True,'description':'Search only the authorized task project and return source excerpts.'},
            {'id':'project.inspect','mode':'read','enabled':True,'description':'Inspect the authorized project and its source inventory.'},
            {'id':'artifact.create','mode':'write','enabled':user['role']!='VIEWER','description':'Create a private, versioned artifact from a permitted agent task.'},
            {'id':'model.generate','mode':'inference','enabled':True,'description':'Use the selected local model. Tools mode requires verified model tool support.'},
            {'id':'program.list','mode':'read','enabled':True,'description':'Discover qualified independent programs when the private gateway is online.'},
            {'id':'program.run','mode':'execute','enabled':user['role']!='VIEWER','description':'Invoke only qualified offline program recipes; requires explicit agent tool permission.'}]

@app.get('/api/v1/integrations')
def integrations(user: User):
    connected = []
    if user['role'] == 'ADMIN':
        connected = db.query("""
            SELECT c.id,c.name,c.client_type,c.model_access,c.webhook_destination IS NOT NULL AS has_webhook
            FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.revoked_at IS NULL AND NOT c.paused
              AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN'
            ORDER BY c.created_at DESC LIMIT 200
        """)
    return {'connected': connected, 'policy':'Optional versioned API connections. No other product is required.'}

# Chat is an independent product module, sharing only local identity and inference.
from .chat import router as chat_router
app.include_router(chat_router)

from .skills import router as skills_router
app.include_router(skills_router)
from .repository_intelligence import router as repository_intelligence_router
app.include_router(repository_intelligence_router)

from .connections import router as connections_router
app.include_router(connections_router)

from .workspace import router as workspace_router
from .files import router as files_router
app.include_router(workspace_router)
app.include_router(files_router)

@app.get('/api/v1/models/inspect')
def inspect_model(model:str,user:User):
    try:return models.inspect_model(model)
    except Exception:raise HTTPException(422,'Model inspection failed. Confirm the model is installed and the provider is reachable.')

@app.get('/api/v1/operations/metrics')
def operation_metrics(user:User):
    ids=[p['id'] for p in access.allowed_projects(user)]
    return {'tasks':db.query('SELECT id,status,model,metrics,created_at,finished_at FROM runs WHERE project_id=ANY(%s) ORDER BY created_at DESC LIMIT 100',(ids,)),
            'chats':db.query('SELECT id,status,model,metrics,created_at,finished_at FROM chat_generations WHERE requested_by=%s ORDER BY created_at DESC LIMIT 100',(user['id'],)),
            'files':db.query("SELECT status,count(*) AS n FROM workspace_files WHERE owner_id=%s OR %s='ADMIN' GROUP BY status",(user['id'],user['role']))}

from .external_connections import router as external_connections_router

app.include_router(external_connections_router)

app.include_router(program_gateway.router)

from . import program_jobs, missions
app.include_router(program_jobs.router)
app.include_router(missions.router)
app.include_router(execution_policy.router)
