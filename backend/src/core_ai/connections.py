"""Admin-managed bearer credentials and durable local inference jobs."""
import re
import secrets
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from . import access, auth, db, runs

router = APIRouter(prefix='/api/v1')
User = Annotated[dict, Depends(auth.session)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Model = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')]
TOKEN = re.compile(r'(?i:Bearer) (coreai_[A-Za-z0-9_-]{43})')


class Connection(BaseModel):
    name: Label
    client_type: Literal['n8n','custom'] = 'custom'
    can_discover: bool = True
    can_submit: bool = True
    can_read: bool = True
    project_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    model: Model | None = None
    allowed_models: list[Model] | None = Field(default=None, min_length=1, max_length=32)
    allow_model_choice: bool = False
    expires_at: AwareDatetime | None = None
    requests_per_minute: int = Field(default=30, ge=1, le=600)
    max_pending: int = Field(default=20, ge=1, le=20)
    timeout_seconds: int = Field(default=300, ge=15, le=300)
    max_output_tokens: int = Field(default=2048, ge=128, le=4096)

    @model_validator(mode='after')
    def validate_models(self):
        if '\0' in self.name:
            raise ValueError('Enter a valid connection name.')
        self.allowed_models = list(dict.fromkeys(self.allowed_models or ([self.model] if self.model else [])))
        if not self.allowed_models or (not self.model and not self.allow_model_choice):
            raise ValueError('Choose allowed models and a default when model selection is fixed.')
        if self.model and self.model not in self.allowed_models:
            raise ValueError('Choose a default from the allowed models.')
        return self


class Job(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
    model: Model | None = None

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, prompt):
        if '\0' in prompt:
            raise ValueError('Enter a text prompt without null characters.')
        return prompt


@router.get('/connections')
def list_connections(user: User):
    access.admin(user)
    return db.query("""
        SELECT c.id,c.name,c.project_id,p.name AS project,c.agent_id,a.name AS agent,c.model,c.allowed_models,
               c.allow_model_choice,c.client_type,c.can_discover,c.can_submit,c.can_read,c.paused,c.expires_at,c.last_used_at,c.requests_per_minute,c.max_pending,
               c.timeout_seconds,c.max_output_tokens,c.created_at,c.revoked_at,
               c.expires_at<=now() AS expired,
               u.enabled AND u.role='ADMIN' AND (p.archived_at IS NULL)
                 AND (c.agent_id IS NULL OR (a.enabled AND a.runtime_mode='analysis')) AS scope_available
        FROM automation_connections c LEFT JOIN projects p ON p.id=c.project_id
        LEFT JOIN agents a ON a.id=c.agent_id JOIN users u ON u.id=c.created_by
        ORDER BY c.created_at DESC
    """)


def analysis_agent(conn, user, agent_id):
    if agent_id is None:
        return {}
    agent = access.agent(conn, user, agent_id)
    if not agent['enabled'] or agent['runtime_mode'] != 'analysis':
        raise HTTPException(422, 'Choose an enabled Analysis agent.')
    return agent


def settings(conn, body, user):
    if body.project_id is not None:
        access.project(conn, user, body.project_id, True)
    analysis_agent(conn, user, body.agent_id)
    return (body.name, body.project_id, body.agent_id, body.model, body.allowed_models,
            body.allow_model_choice, body.expires_at, body.requests_per_minute, body.max_pending,
            body.timeout_seconds, body.max_output_tokens, body.client_type, body.can_discover, body.can_submit, body.can_read)


@router.post('/connections', status_code=201)
def create_connection(body: Connection, user: User):
    access.admin(user)
    ident, token = uuid.uuid4(), 'coreai_' + secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO automation_connections(id,token_hash,created_by,name,project_id,agent_id,model,allowed_models,
                allow_model_choice,expires_at,requests_per_minute,max_pending,timeout_seconds,max_output_tokens,
                client_type,can_discover,can_submit,can_read)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (ident, auth.token_hash(token), user['id'], *settings(conn, body, user)))
        db.event('connection.created', user['id'], {'id': str(ident)}, conn=conn)
    return {'id': ident, 'token': token}


@router.put('/connections/{ident}')
def update_connection(ident: uuid.UUID, body: Connection, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute("""
            UPDATE automation_connections SET name=%s,project_id=%s,agent_id=%s,model=%s,allowed_models=%s,
                allow_model_choice=%s,expires_at=%s,requests_per_minute=%s,max_pending=%s,
                timeout_seconds=%s,max_output_tokens=%s,client_type=%s,can_discover=%s,can_submit=%s,can_read=%s
            WHERE id=%s AND revoked_at IS NULL RETURNING id
        """, (*settings(conn, body, user), ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Active connection not found.')
        db.event('connection.updated', user['id'], {'id': str(ident)}, conn=conn)
    return {'ok': True}


class Pause(BaseModel):
    paused: bool


@router.put('/connections/{ident}/pause')
def pause_connection(ident: uuid.UUID, body: Pause, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute('''
            UPDATE automation_connections SET paused=%s
            WHERE id=%s AND revoked_at IS NULL RETURNING id
        ''', (body.paused, ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Active connection not found.')
        db.event('connection.paused' if body.paused else 'connection.resumed', user['id'], {'id': str(ident)}, conn=conn)
    return {'ok': True}


@router.post('/connections/{ident}/rotate')
def rotate_connection(ident: uuid.UUID, user: User):
    access.admin(user)
    token = 'coreai_' + secrets.token_urlsafe(32)
    with db.connect() as conn:
        row = conn.execute('''
            UPDATE automation_connections SET token_hash=%s
            WHERE id=%s AND revoked_at IS NULL RETURNING id
        ''', (auth.token_hash(token), ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Active connection not found.')
        db.event('connection.rotated', user['id'], {'id': str(ident)}, conn=conn)
    return {'id': ident, 'token': token}


@router.post('/connections/{ident}/revoke')
def revoke_connection(ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute('''
            UPDATE automation_connections SET revoked_at=now()
            WHERE id=%s AND revoked_at IS NULL RETURNING id
        ''', (ident,)).fetchone()
        if row:
            db.event('connection.revoked', user['id'], {'id': str(ident)}, conn=conn)
        elif not conn.execute('SELECT id FROM automation_connections WHERE id=%s', (ident,)).fetchone():
            raise HTTPException(404, 'Connection not found.')
    return {'ok': True}


@router.get('/connections/{ident}/activity')
def connection_activity(ident: uuid.UUID, user: User):
    access.admin(user)
    return db.query("""
        SELECT id,request_id,model,status,created_at,finished_at,
            EXTRACT(EPOCH FROM finished_at-started_at) AS duration_seconds,
            CASE WHEN status='FAILED' THEN 'Inference failed' END AS error
        FROM runs WHERE connection_id=%s ORDER BY created_at DESC LIMIT 100
    """, (ident,))


def authenticated_connection(conn, request):
    match = TOKEN.fullmatch(request.headers.get('authorization', ''))
    if match:
        connection = conn.execute("""
            SELECT c.*, u.role FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.token_hash=%s AND c.revoked_at IS NULL AND NOT c.paused
              AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN'
            FOR UPDATE OF c
        """, (auth.token_hash(match[1]),)).fetchone()
        if connection:
            conn.execute('UPDATE automation_connections SET last_used_at=now() WHERE id=%s', (connection['id'],))
            return connection
    raise HTTPException(401, 'Provide an active connection key.', headers={'WWW-Authenticate': 'Bearer'})


def selectable_models(connection):
    return connection['allowed_models'] if connection['allow_model_choice'] else [connection['model']]


@router.get('/automation/models')
def discover_models(request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_discover']:
            raise HTTPException(403, 'Model discovery is disabled for this key.')
        return {'models': selectable_models(connection), 'default': connection['model']}


def enqueue_job(conn, connection, body):
    if not connection['can_submit']:
        raise HTTPException(403, 'Job submission is disabled for this key.')
    previous = conn.execute("""
        SELECT id,prompt,model FROM runs WHERE connection_id=%s AND request_id=%s
    """, (connection['id'], body.request_id)).fetchone()
    if previous:
        if body.prompt != previous['prompt'] or (body.model is not None and body.model != previous['model']):
            raise HTTPException(409, 'This request ID was used with a different prompt or model.')
        return previous['id']

    model = body.model or connection['model']
    if model is None:
        raise HTTPException(422, 'Select a model for this request. The connection has no default.')
    if model not in selectable_models(connection):
        raise HTTPException(403, 'This connection cannot use the requested model.')
    usage = conn.execute("""
        SELECT count(*) FILTER (WHERE created_at>now()-interval '1 minute') AS recent,
               count(*) FILTER (WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS pending
        FROM runs WHERE connection_id=%s
          AND (created_at>now()-interval '1 minute' OR status IN ('QUEUED','RUNNING','CANCEL_REQUESTED'))
    """, (connection['id'],)).fetchone()
    if usage['recent'] >= connection['requests_per_minute']:
        raise HTTPException(429, 'Connection request limit reached.', headers={'Retry-After': '60'})
    if usage['pending'] >= connection['max_pending']:
        raise HTTPException(409, 'Connection queue is full. Wait for an existing job.')
    user = {'id': connection['created_by'], 'role': connection['role']}
    if connection['project_id'] is not None:
        access.project(conn, user, connection['project_id'], True)
    agent = analysis_agent(conn, user, connection['agent_id'])
    return runs.enqueue(conn, project_id=connection['project_id'], agent=agent, prompt=body.prompt,
                        model=model, user_id=user['id'], connection_id=connection['id'], request_id=body.request_id,
                        timeout_seconds=connection['timeout_seconds'], max_output_tokens=connection['max_output_tokens'])


@router.post('/automation/jobs', status_code=202)
def submit_job(body: Job, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        return {'id': enqueue_job(conn, connection, body)}


@router.post('/connections/{ident}/test', status_code=202)
def test_connection(ident: uuid.UUID, body: Job, user: User):
    access.admin(user)
    with db.connect() as conn:
        connection = conn.execute("""
            SELECT c.*,u.role FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.id=%s AND c.revoked_at IS NULL AND NOT c.paused AND u.enabled AND u.role='ADMIN'
              AND (c.expires_at IS NULL OR c.expires_at>now()) FOR UPDATE OF c
        """, (ident,)).fetchone()
        if not connection:
            raise HTTPException(409, 'The connection must be active before testing.')
        return {'id': enqueue_job(conn, connection, body)}


def connection_job(conn, connection_id, ident):
    job = conn.execute("""
        SELECT id,model,status,output,error,created_at,finished_at
        FROM runs WHERE id=%s AND connection_id=%s
    """, (ident, connection_id)).fetchone()
    if not job:
        raise HTTPException(404, 'Job not found.')
    return job


@router.get('/connections/{connection_id}/jobs/{ident}')
def admin_job(connection_id: uuid.UUID, ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        return connection_job(conn, connection_id, ident)


@router.get('/automation/jobs/{ident}')
def get_job(ident: uuid.UUID, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_read']:
            raise HTTPException(403, 'Job result access is disabled for this key.')
        return connection_job(conn, connection['id'], ident)
