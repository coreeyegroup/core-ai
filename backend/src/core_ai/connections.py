"""Admin-managed bearer credentials for inbound analysis jobs."""
import re
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from . import access, auth, db, runs

router = APIRouter(prefix='/api/v1')
User = Annotated[dict, Depends(auth.session)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TOKEN = re.compile(r'(?i:Bearer) (coreai_[A-Za-z0-9_-]{43})')


class Connection(BaseModel):
    name: Label
    project_id: uuid.UUID
    agent_id: uuid.UUID
    model: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9_.:/-]+$')


class Job(BaseModel):
    model_config = ConfigDict(extra='forbid')

    request_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


@router.get('/connections')
def list_connections(user: User):
    access.admin(user)
    return db.query("""
        SELECT c.id,c.name,c.project_id,p.name AS project,c.agent_id,a.name AS agent,c.model,
               c.created_at,c.revoked_at,u.enabled AND u.role='ADMIN' AND a.enabled
                 AND a.runtime_mode='analysis' AS scope_available
        FROM automation_connections c JOIN projects p ON p.id=c.project_id
        JOIN agents a ON a.id=c.agent_id JOIN users u ON u.id=c.created_by
        ORDER BY c.created_at DESC
    """)


def analysis_agent(conn, user, agent_id):
    agent = access.agent(conn, user, agent_id)
    if not agent['enabled'] or agent['runtime_mode'] != 'analysis':
        raise HTTPException(422, 'Choose an enabled Analysis agent.')
    return agent


@router.post('/connections', status_code=201)
def create_connection(body: Connection, user: User):
    access.admin(user)
    ident = uuid.uuid4()
    token = 'coreai_' + secrets.token_urlsafe(32)
    with db.connect() as conn:
        access.project(conn, user, body.project_id, True)
        analysis_agent(conn, user, body.agent_id)
        conn.execute("""
            INSERT INTO automation_connections(id,name,token_hash,project_id,agent_id,model,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (ident, body.name, auth.token_hash(token), body.project_id, body.agent_id, body.model, user['id']))
        db.event('connection.created', user['id'], {'id': str(ident)}, conn=conn)
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


def authenticated_connection(conn, request):
    match = TOKEN.fullmatch(request.headers.get('authorization', ''))
    if match:
        connection = conn.execute("""
            SELECT c.id,c.project_id,c.agent_id,c.model,c.created_by,u.role
            FROM automation_connections c JOIN users u ON u.id=c.created_by
            WHERE c.token_hash=%s AND c.revoked_at IS NULL AND u.enabled AND u.role='ADMIN'
            FOR UPDATE OF c
        """, (auth.token_hash(match[1]),)).fetchone()
        if connection:
            return connection
    raise HTTPException(401, 'Provide an active connection key.', headers={'WWW-Authenticate': 'Bearer'})


@router.post('/automation/jobs', status_code=202)
def submit_job(body: Job, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        previous = conn.execute("""
            SELECT id, prompt FROM runs WHERE connection_id=%s AND request_id=%s
        """, (connection['id'], body.request_id)).fetchone()
        if previous:
            if body.prompt != previous['prompt']:
                raise HTTPException(409, 'This request ID was used with a different prompt.')
            return {'id': previous['id']}
        user = {'id': connection['created_by'], 'role': connection['role']}
        agent = analysis_agent(conn, user, connection['agent_id'])
        ident = runs.enqueue(conn, project_id=connection['project_id'], agent=agent,
                             prompt=body.prompt, model=connection['model'], user_id=user['id'],
                             connection_id=connection['id'], request_id=body.request_id)
    return {'id': ident}


@router.get('/automation/jobs/{ident}')
def get_job(ident: uuid.UUID, request: Request):
    with db.connect() as conn:
        connection = authenticated_connection(conn, request)
        job = conn.execute("""
            SELECT id,status,output,error,created_at,finished_at
            FROM runs WHERE id=%s AND connection_id=%s
        """, (ident, connection['id'])).fetchone()
    if not job:
        raise HTTPException(404, 'Job not found.')
    return job
