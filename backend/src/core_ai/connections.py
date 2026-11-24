"""Admin-managed bearer credentials and durable local inference jobs."""
import hmac
import json
import re
import secrets
import uuid
from typing import Annotated, Literal

import httpx
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator, model_validator

from . import access, auth, db, runs, webhooks, key_storage, models

router = APIRouter(prefix='/api/v1')
User = Annotated[dict, Depends(auth.session)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Model = Annotated[str, StringConstraints(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')]
Operation = Literal['generation', 'embedding']
RequestId = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')]
TOKEN = re.compile(r'(?i:Bearer) (coreai_[A-Za-z0-9_-]{43})')


class ModelPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    requests_per_minute: int | None = Field(default=None, ge=1, le=600)
    max_pending: int | None = Field(default=None, ge=1, le=20)
    timeout_seconds: int | None = Field(default=None, ge=15, le=300)
    max_output_tokens: int | None = Field(default=None, ge=128, le=4096)
    context_tokens: int | None = Field(default=None, ge=1024, le=32768)


class Connection(BaseModel):
    name: Label
    client_type: Literal['n8n','custom','webhook','platform'] = 'custom'
    webhook_destination: str | None = Field(default=None,pattern=webhooks.DESTINATION_PATTERN)
    can_discover: bool = True
    can_submit: bool = True
    can_read: bool = True
    can_cancel: bool = False
    can_embed: bool = False
    project_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    model: Model | None = None
    allowed_models: list[Model] | None = Field(default=None, max_length=32)
    model_access: Literal['selected', 'all'] = 'selected'
    model_policies: dict[Model, ModelPolicy] = Field(default_factory=dict, max_length=256)
    allow_model_choice: bool = False
    expires_at: AwareDatetime | None = None
    requests_per_minute: int = Field(default=30, ge=1, le=600)
    max_pending: int = Field(default=20, ge=1, le=20)
    timeout_seconds: int = Field(default=300, ge=15, le=300)
    max_output_tokens: int = Field(default=2048, ge=128, le=4096)
    context_tokens: int = Field(default=8192, ge=1024, le=32768)

    @model_validator(mode='after')
    def validate_models(self):
        if '\0' in self.name:
            raise ValueError('Enter a valid connection name.')
        self.allowed_models = list(dict.fromkeys(self.allowed_models or ([self.model] if self.model else [])))
        return self

    def check_scope(self):
        if not self.model and not self.allow_model_choice:
            raise HTTPException(422, 'Choose a default when model selection is fixed.')
        if self.model_access == 'selected' and (
            not self.allowed_models or (self.model and self.model not in self.allowed_models)
        ):
            raise HTTPException(422, 'Choose allowed models and select a default from that list.')
        if self.model and not self.model_policies.get(self.model, ModelPolicy()).enabled:
            raise HTTPException(422, 'Enable the default model or select a different one.')


class ConnectionCreate(Connection):
    save_for_reveal: bool = False


class Job(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: RequestId
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
               c.model_access,c.model_policies,c.can_cancel,c.can_embed,c.allow_model_choice,c.client_type,c.webhook_destination,c.can_discover,c.can_submit,c.can_read,c.paused,c.expires_at,c.last_used_at,c.requests_per_minute,c.max_pending,
               c.timeout_seconds,c.max_output_tokens,c.context_tokens,c.created_at,c.revoked_at,
               CASE WHEN c.previous_valid_until>now() THEN c.previous_valid_until END AS overlap_until,
               c.expires_at<=now() AS expired, c.encrypted_token IS NOT NULL AS can_reveal,
               u.enabled AND u.role='ADMIN' AND (p.archived_at IS NULL AND p.deleted_at IS NULL)
                 AND (c.agent_id IS NULL OR (a.enabled AND a.runtime_mode='analysis')) AS scope_available
        FROM automation_connections c LEFT JOIN projects p ON p.id=c.project_id
        LEFT JOIN agents a ON a.id=c.agent_id JOIN users u ON u.id=c.created_by
        ORDER BY c.created_at DESC
    """)


@router.get('/connections/key-storage')
def connection_key_storage(user: User):
    access.admin(user)
    return {'available':key_storage.configured()}


@router.get('/connections/webhook-destinations')
def webhook_destinations(user: User):
    access.admin(user)
    return sorted(webhooks.destinations())


def analysis_agent(conn, user, agent_id):
    if agent_id is None:
        return {}
    agent = access.agent(conn, user, agent_id)
    if not agent['enabled'] or agent['runtime_mode'] != 'analysis':
        raise HTTPException(422, 'Choose an enabled Analysis agent.')
    return agent


def settings(conn, body, user, previous=None):
    previous = previous or {}
    body.check_scope()
    if body.project_id is not None and body.project_id != previous.get('project_id'):
        access.project(conn, user, body.project_id, True)
    if body.agent_id != previous.get('agent_id'):
        analysis_agent(conn, user, body.agent_id)
    if (body.webhook_destination and body.webhook_destination != previous.get('webhook_destination')
            and body.webhook_destination not in webhooks.destinations()):
        raise HTTPException(422, 'Select a configured webhook destination.')
    return (body.name, body.project_id, body.agent_id, body.model, body.allowed_models,
            body.allow_model_choice, body.expires_at, body.requests_per_minute, body.max_pending,
            body.timeout_seconds, body.max_output_tokens, body.client_type, body.can_discover, body.can_submit, body.can_read, body.webhook_destination,
            body.model_access, Jsonb({name: policy.model_dump(exclude_defaults=True)
                                    for name, policy in body.model_policies.items()}), body.can_cancel, body.can_embed, body.context_tokens)


@router.post('/connections', status_code=201)
def create_connection(body: ConnectionCreate, user: User):
    access.admin(user)
    ident, token = uuid.uuid4(), 'coreai_' + secrets.token_urlsafe(32)
    encrypted = key_storage.transform(token.encode('ascii')) if body.save_for_reveal else None
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO automation_connections(id,token_hash,created_by,name,project_id,agent_id,model,allowed_models,
                allow_model_choice,expires_at,requests_per_minute,max_pending,timeout_seconds,max_output_tokens,
                client_type,can_discover,can_submit,can_read,webhook_destination,model_access,model_policies,can_cancel,can_embed,context_tokens,encrypted_token)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (ident, auth.token_hash(token), user['id'], *settings(conn, body, user), encrypted))
        db.event('connection.created', user['id'], {'id': str(ident)}, conn=conn)
    return {'id': ident, 'token': token}


@router.put('/connections/{ident}')
def update_connection(ident: uuid.UUID, body: Connection, user: User):
    access.admin(user)
    with db.connect() as conn:
        previous = conn.execute("""
            SELECT project_id,agent_id,webhook_destination,model_access,model_policies,can_cancel,can_embed,context_tokens FROM automation_connections
            WHERE id=%s AND revoked_at IS NULL FOR UPDATE
        """, (ident,)).fetchone()
        if not previous:
            raise HTTPException(404, 'Active connection not found.')
        omitted = {field: previous[field] for field in ('model_access', 'model_policies', 'can_cancel', 'can_embed', 'context_tokens')
                   if field not in body.model_fields_set}
        if omitted:
            body = Connection.model_validate({**body.model_dump(), **omitted})
        conn.execute("""
            UPDATE automation_connections SET name=%s,project_id=%s,agent_id=%s,model=%s,allowed_models=%s,
                allow_model_choice=%s,expires_at=%s,requests_per_minute=%s,max_pending=%s,
                timeout_seconds=%s,max_output_tokens=%s,client_type=%s,can_discover=%s,can_submit=%s,can_read=%s,webhook_destination=%s,
                model_access=%s,model_policies=%s,can_cancel=%s,can_embed=%s,context_tokens=%s
            WHERE id=%s
        """, (*settings(conn, body, user, previous), ident))
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


class Rotate(BaseModel):
    save_for_reveal: bool | None = None
    overlap_minutes: int = Field(default=0, ge=0, le=1440)


@router.post('/connections/{ident}/rotate')
def rotate_connection(ident: uuid.UUID, user: User, body: Rotate | None = None):
    access.admin(user)
    token = 'coreai_' + secrets.token_urlsafe(32)
    with db.connect() as conn:
        row = conn.execute('SELECT encrypted_token IS NOT NULL AS saved FROM automation_connections WHERE id=%s AND revoked_at IS NULL FOR UPDATE',(ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Active connection not found.')
        save = body.save_for_reveal if body and body.save_for_reveal is not None else row['saved']
        encrypted = key_storage.transform(token.encode('ascii')) if save else None
        overlap = body.overlap_minutes if body else 0
        rotation = conn.execute("""
            UPDATE automation_connections SET
                previous_token_hash=CASE WHEN %s>0 THEN token_hash END,
                previous_valid_until=CASE WHEN %s>0 THEN now()+make_interval(mins => %s) END,
                token_hash=%s,encrypted_token=%s
            WHERE id=%s RETURNING previous_valid_until
        """, (overlap, overlap, overlap, auth.token_hash(token), encrypted, ident)).fetchone()
        db.event('connection.rotated', user['id'], {'id': str(ident), 'overlap_minutes': overlap}, conn=conn)
    return {'id': ident, 'token': token, 'overlap_until': rotation['previous_valid_until']}


@router.post('/connections/{ident}/end-overlap')
def end_key_overlap(ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute("""UPDATE automation_connections SET previous_token_hash=NULL, previous_valid_until=NULL
            WHERE id=%s AND revoked_at IS NULL RETURNING id""", (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Active connection not found.')
        db.event('connection.overlap_ended', user['id'], {'id': str(ident)}, conn=conn)
    return {'ok': True}



class Reveal(BaseModel):
    password: SecretStr


@router.post('/connections/{ident}/reveal')
def reveal_key(ident: uuid.UUID, body: Reveal, user: User):
    access.admin(user)
    password = body.password.get_secret_value()
    if not 1 <= len(password) <= 256:
        raise HTTPException(403, 'Enter your current administrator password.')
    auth.confirm_admin_password(user,password)
    with db.connect() as conn:
        row = conn.execute('SELECT token_hash,encrypted_token FROM automation_connections WHERE id=%s AND revoked_at IS NULL FOR UPDATE',(ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Unrevoked connection not found.')
        if row['encrypted_token'] is None:
            raise HTTPException(409, 'No recoverable copy exists. Rotate the key with encrypted storage enabled.')
        token = key_storage.transform(row['encrypted_token'],decrypt=True).decode('ascii',errors='replace')
        if not hmac.compare_digest(auth.token_hash(token),row['token_hash']):
            raise HTTPException(503, 'Encrypted key does not match the current connection.')
        db.event('connection.key_revealed', user['id'], {'id':str(ident)}, conn=conn)
    return {'id':ident, 'token':token}


@router.post('/connections/{ident}/revoke')
def revoke_connection(ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute('''
            UPDATE automation_connections SET revoked_at=now(),encrypted_token=NULL,previous_token_hash=NULL,previous_valid_until=NULL
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
        SELECT r.id,r.request_id,r.model,r.status,r.created_at,r.finished_at,d.status AS webhook_status,
            EXTRACT(EPOCH FROM r.finished_at-r.started_at) AS duration_seconds,
            CASE WHEN r.status='FAILED' THEN 'Inference failed' END AS error
        FROM runs r LEFT JOIN automation_webhook_deliveries d ON d.run_id=r.id
        WHERE r.connection_id=%s ORDER BY r.created_at DESC LIMIT 100
    """, (ident,))


def authenticated_connection(conn, request):
    match = TOKEN.fullmatch(request.headers.get('authorization', ''))
    if match:
        digest = auth.token_hash(match[1])
        connection = conn.execute("""
            SELECT c.*, u.role FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE (c.token_hash=%s OR (c.previous_token_hash=%s AND c.previous_valid_until>now()))
              AND c.revoked_at IS NULL AND NOT c.paused
              AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN'
            FOR UPDATE OF c
        """, (digest, digest)).fetchone()
        if connection:
            conn.execute('UPDATE automation_connections SET last_used_at=now() WHERE id=%s', (connection['id'],))
            return connection
    raise HTTPException(401, 'Provide an active connection key.', headers={'WWW-Authenticate': 'Bearer'})


def installed_models(operation):
    try:
        catalog = models.with_capabilities(models.list_models())
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise HTTPException(503, 'The model catalog is temporarily unavailable.') from exc
    supports = models.supports_embedding if operation == 'embedding' else models.supports_generation
    return sorted({
        item['name'] for item in catalog['models']
        if isinstance(item.get('name'), str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', item['name'])
        and supports(item)
    })


def selectable_models(connection, operation='generation'):
    if operation == 'embedding' and not connection['can_embed']:
        return []
    candidates = connection['allowed_models']
    if connection['model_access'] == 'all' or operation == 'embedding':
        installed = installed_models(operation)
        candidates = (installed if connection['model_access'] == 'all' else
                      [name for name in candidates if name in installed])
    if not connection['allow_model_choice']:
        candidates = [connection['model']] if connection['model'] in candidates else []
    return [name for name in candidates if connection['model_policies'].get(name, {}).get('enabled', True)]


def model_limits(connection, name):
    policy = connection['model_policies'].get(name, {})
    return {field: min(connection[field], policy.get(field) or connection[field]) for field in (
        'requests_per_minute', 'max_pending', 'timeout_seconds', 'max_output_tokens', 'context_tokens'
    )}


@router.get('/automation/models')
def discover_models(request: Request, operation: Operation = 'generation'):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_discover']:
            raise HTTPException(403, 'Model discovery is disabled for this key.')
        names = selectable_models(connection, operation)
        return {'models': names, 'default': connection['model'] if connection['model'] in names else None}


@router.get('/automation/model-policies')
def discover_model_policies(request: Request, operation: Operation = 'generation'):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_discover']:
            raise HTTPException(403, 'Model discovery is disabled for this key.')
        return {'model_access': connection['model_access'], 'caller_can_choose': connection['allow_model_choice'],
                'limits': {name: model_limits(connection, name) for name in selectable_models(connection, operation)}}


@router.get('/connections/{ident}/models')
def admin_models(ident: uuid.UUID, user: User, operation: Operation = 'generation'):
    access.admin(user)
    connection = db.query("""SELECT model, allowed_models, model_access, model_policies, allow_model_choice, can_embed
                             FROM automation_connections WHERE id=%s""", (ident,), one=True)
    if not connection:
        raise HTTPException(404, 'Connection not found.')
    names = selectable_models(connection, operation)
    return {'models': names, 'default': connection['model'] if connection['model'] in names else None}


def enqueue_job(conn, connection, body, *, notify=False, retry_of=None, operation='generation'):
    if operation == 'generation' and not connection['can_submit']:
        raise HTTPException(403, 'Generation submission is disabled for this key.')
    if operation == 'embedding' and not connection['can_embed']:
        raise HTTPException(403, 'Embedding submission is disabled for this key.')
    previous = conn.execute("""
        SELECT id,prompt,model,retry_of,operation FROM runs WHERE connection_id=%s AND request_id=%s
    """, (connection['id'], body.request_id)).fetchone()
    if previous:
        if (body.prompt != previous['prompt'] or retry_of != previous['retry_of'] or operation != previous['operation']
                or (body.model is not None and body.model != previous['model'])):
            raise HTTPException(409, 'This request ID was used with a different prompt or model.')
        return previous['id']

    model = body.model or connection['model']
    if model is None:
        raise HTTPException(422, 'Select a model for this request. The connection has no default.')
    if model not in selectable_models(connection, operation):
        raise HTTPException(403, 'This connection cannot use the requested model.')
    limits = model_limits(connection, model)
    usage = conn.execute("""
        SELECT count(*) FILTER (WHERE created_at>now()-interval '1 minute') AS recent,
               count(*) FILTER (WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS pending,
               count(*) FILTER (WHERE model=%s AND created_at>now()-interval '1 minute') AS model_recent,
               count(*) FILTER (WHERE model=%s AND status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS model_pending
        FROM runs WHERE connection_id=%s
          AND (created_at>now()-interval '1 minute' OR status IN ('QUEUED','RUNNING','CANCEL_REQUESTED'))
    """, (model, model, connection['id'])).fetchone()
    if usage['recent'] >= connection['requests_per_minute']:
        raise HTTPException(429, 'Connection request limit reached.', headers={'Retry-After': '60'})
    if usage['pending'] >= connection['max_pending']:
        raise HTTPException(409, 'Connection queue is full. Wait for an existing job.')
    if usage['model_recent'] >= limits['requests_per_minute']:
        raise HTTPException(429, 'Model request limit reached for this connection.', headers={'Retry-After': '60'})
    if usage['model_pending'] >= limits['max_pending']:
        raise HTTPException(409, 'The model queue for this connection is full.')
    user = {'id': connection['created_by'], 'role': connection['role']}
    if connection['project_id'] is not None:
        access.project(conn, user, connection['project_id'], True)
    agent = analysis_agent(conn, user, connection['agent_id'])
    job_id = runs.enqueue(conn, project_id=connection['project_id'], agent=agent, prompt=body.prompt,
                        model=model, user_id=user['id'], connection_id=connection['id'], request_id=body.request_id,
                        timeout_seconds=limits['timeout_seconds'], max_output_tokens=limits['max_output_tokens'],
                        context_tokens=limits['context_tokens'], retry_of=retry_of, operation=operation)
    if notify and connection['webhook_destination']:
        conn.execute('INSERT INTO automation_webhook_deliveries(run_id,destination) VALUES (%s,%s)',
                     (job_id,connection['webhook_destination']))
    return job_id


@router.post('/automation/jobs', status_code=202)
def submit_job(body: Job, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        return {'id': enqueue_job(conn, connection, body, notify=True)}


class EmbeddingJob(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: RequestId
    input: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]
    model: Model | None = None

    @field_validator('input')
    @classmethod
    def validate_input(cls, value):
        return Job.validate_prompt(value)


@router.post('/automation/embeddings', status_code=202)
def submit_embedding(body: EmbeddingJob, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        return {'id': enqueue_job(conn, connection, Job(request_id=body.request_id, prompt=body.input, model=body.model),
                                  notify=True, operation='embedding')}


@router.post('/connections/{ident}/test', status_code=202)
def test_connection(ident: uuid.UUID, body: Job, user: User, operation: Operation = 'generation'):
    access.admin(user)
    with db.connect() as conn:
        connection = conn.execute("""
            SELECT c.*,u.role FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.id=%s AND c.revoked_at IS NULL AND NOT c.paused AND u.enabled AND u.role='ADMIN'
              AND (c.expires_at IS NULL OR c.expires_at>now()) FOR UPDATE OF c
        """, (ident,)).fetchone()
        if not connection:
            raise HTTPException(409, 'The connection must be active before testing.')
        return {'id': enqueue_job(conn, connection, body, operation=operation)}


def connection_job(conn, connection_id, ident):
    job = conn.execute("""
        SELECT id,model,operation,status,output,error,created_at,finished_at
        FROM runs WHERE id=%s AND connection_id=%s
    """, (ident, connection_id)).fetchone()
    if not job:
        raise HTTPException(404, 'Job not found.')
    if job['operation'] == 'embedding' and job['output'] is not None:
        job['embeddings'] = json.loads(job.pop('output'))
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

def model_usage(conn, connection_id):
    return conn.execute("""
        SELECT model, count(*) AS requests,
            count(*) FILTER (WHERE created_at>now()-interval '1 minute') AS recent_requests,
            count(*) FILTER (WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS pending,
            count(*) FILTER (WHERE status='SUCCEEDED') AS succeeded,
            count(*) FILTER (WHERE status='FAILED') AS failed,
            count(*) FILTER (WHERE status='CANCELLED') AS cancelled,
            COALESCE(sum(trunc((metrics->>'prompt_eval_count')::numeric)),0) AS measured_input_tokens,
            COALESCE(sum(trunc((metrics->>'eval_count')::numeric)),0) AS measured_output_tokens
        FROM runs WHERE connection_id=%s AND (
            created_at>now()-interval '30 days' OR status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')
        ) GROUP BY model ORDER BY model
    """, (connection_id,)).fetchall()


@router.get('/automation/usage')
def connection_usage(request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_read']:
            raise HTTPException(403, 'Usage access is disabled for this key.')
        return {'window_days': 30, 'models': model_usage(conn, connection['id'])}


@router.get('/connections/{connection_id}/usage')
def admin_usage(connection_id: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        if not conn.execute('SELECT id FROM automation_connections WHERE id=%s', (connection_id,)).fetchone():
            raise HTTPException(404, 'Connection not found.')
        return {'window_days': 30, 'models': model_usage(conn, connection_id)}


@router.post('/automation/jobs/{ident}/cancel')
def cancel_job(ident: uuid.UUID, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not connection['can_cancel']:
            raise HTTPException(403, 'Job cancellation is disabled for this key.')
        return runs.cancel(conn, ident, connection['created_by'], connection_id=connection['id'])


@router.post('/connections/{connection_id}/jobs/{ident}/cancel')
def admin_cancel_job(connection_id: uuid.UUID, ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        return runs.cancel(conn, ident, user['id'], connection_id=connection_id)

@router.post('/connections/{connection_id}/jobs/{ident}/webhook/replay', status_code=202)
def replay_webhook(connection_id: uuid.UUID, ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute("""
            SELECT d.status,d.destination,d.attempts,coalesce(
                c.webhook_destination=d.destination AND NOT c.paused AND c.revoked_at IS NULL
                AND (c.expires_at IS NULL OR c.expires_at>now()) AND u.enabled AND u.role='ADMIN',
                false) AS active
            FROM automation_webhook_deliveries d JOIN runs r ON r.id=d.run_id
            JOIN automation_connections c ON c.id=r.connection_id JOIN users u ON u.id=c.created_by
            WHERE d.run_id=%s AND c.id=%s FOR UPDATE OF d,c
        """, (ident, connection_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Webhook delivery not found.')
        if row['status'] not in ('FAILED', 'CANCELLED') or not row['active'] or row['destination'] not in webhooks.destinations():
            raise HTTPException(409, 'Replay requires a failed or cancelled delivery and an active, unchanged destination.')
        conn.execute("""UPDATE automation_webhook_deliveries SET status='PENDING',attempts=0,
                        next_attempt_at=now(),updated_at=now() WHERE run_id=%s""", (ident,))
        db.event('webhook.replayed', user['id'], {'previous_attempts': row['attempts']}, ident, conn)
    return {'status': 'PENDING'}

class Retry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: RequestId


@router.post('/automation/jobs/{ident}/retry', status_code=202)
def retry_job(ident: uuid.UUID, body: Retry, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        if not (connection['can_submit'] or connection['can_embed']):
            raise HTTPException(403, 'Job submission is disabled for this key.')
        source = conn.execute("""
            SELECT status,request_id,prompt,model,operation FROM runs WHERE id=%s AND connection_id=%s
        """, (ident, connection['id'])).fetchone()
        if not source:
            raise HTTPException(404, 'Job not found.')
        if source['status'] not in ('FAILED', 'CANCELLED') or body.request_id == source['request_id']:
            raise HTTPException(409, 'Retry requires a failed or cancelled job and a new request ID.')
        return {'id': enqueue_job(conn, connection, Job(
            request_id=body.request_id, prompt=source['prompt'], model=source['model']
        ), notify=True, retry_of=ident, operation=source['operation'])}


@router.get('/automation/openapi.json', include_in_schema=False)
def automation_schema():
    document = get_openapi(title='CORE-AI Automation API', version='1',
                           routes=[r for r in router.routes if r.path.startswith('/api/v1/automation/')])
    document.setdefault('components', {})['securitySchemes'] = {
        'ConnectionKey': {'type': 'http', 'scheme': 'bearer'}
    }
    document['security'] = [{'ConnectionKey': []}]
    return document
