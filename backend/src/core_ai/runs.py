"""Shared queue admission for workspace and automation jobs."""
import os
import uuid

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import db


def enqueue(conn, *, project_id, agent, prompt, model, user_id, connection_id=None, request_id=None,
            timeout_seconds=300, max_output_tokens=2048, context_tokens=8192, retry_of=None, operation='generation', scheduled=False):
    if scheduled:
        conn.execute('SELECT pg_advisory_xact_lock(187875435)')
    else:
        admit(conn, automation=connection_id is not None)

    ident = uuid.uuid4()
    conn.execute("""
        INSERT INTO runs(id,project_id,agent_id,agent_version,instructions,prompt,model,status,
                         requested_by,runtime_mode,tools,connection_id,request_id,timeout_seconds,max_output_tokens,context_tokens,retry_of,operation)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (ident, project_id, agent.get('id'), agent.get('version'), agent.get('instructions', ''), prompt, model,
          'SCHEDULED' if scheduled else 'QUEUED', user_id, agent.get('runtime_mode', 'analysis'), Jsonb(agent.get('tools', [])), connection_id, request_id,
          timeout_seconds, max_output_tokens, context_tokens, retry_of, operation))
    detail = {'agent_version': agent.get('version')}
    if connection_id is not None:
        detail['connection_id'] = str(connection_id)
    db.event('run.scheduled' if scheduled else 'run.queued', user_id, detail, ident, conn)
    return ident

def admit(conn, *, automation=False):
    conn.execute('SELECT pg_advisory_xact_lock(187875435)')
    usage = conn.execute("""
        SELECT count(*) + (SELECT count(*) FROM chat_generations
            WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS total,
            count(*) FILTER (WHERE connection_id IS NOT NULL) AS automation
        FROM runs WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')
    """).fetchone()
    total = queue_setting('CORE_AI_QUEUE_CAPACITY', default=20, minimum=1, maximum=500)
    reserve = queue_setting('CORE_AI_WORKSPACE_QUEUE_RESERVE', default=4, minimum=0, maximum=total-1)
    if usage['total'] >= total:
        raise HTTPException(409, 'The inference queue is full. Wait or cancel an existing task.')
    if automation and usage['automation'] >= total-reserve:
        raise HTTPException(409, 'The API queue is full. Wait or cancel an existing API job.')


def queue_setting(name, *, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        value = default
    return min(maximum, max(minimum, value))


def cancel(conn, ident, actor, *, connection_id):
    row = conn.execute('SELECT status FROM runs WHERE id=%s AND connection_id=%s FOR UPDATE',
                       (ident, connection_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Job not found.')
    if row['status'] in ('CANCELLED', 'CANCEL_REQUESTED'):
        return row
    if row['status'] not in ('QUEUED', 'RUNNING'):
        raise HTTPException(409, 'The job has already finished.')
    status = 'CANCELLED' if row['status'] == 'QUEUED' else 'CANCEL_REQUESTED'
    conn.execute("""UPDATE runs SET status=%s, finished_at=CASE WHEN %s='CANCELLED' THEN now() END
                    WHERE id=%s""", (status, status, ident))
    db.event('run.cancel_requested', actor, {'connection_id': str(connection_id)}, ident, conn)
    return {'status': status}
