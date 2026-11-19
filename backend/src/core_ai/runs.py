"""Shared queue admission for workspace and automation jobs."""
import uuid

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import db


def enqueue(conn, *, project_id, agent, prompt, model, user_id, connection_id=None, request_id=None):
    conn.execute('SELECT pg_advisory_xact_lock(187875435)')
    pending = conn.execute("""
        SELECT (SELECT count(*) FROM runs WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) +
        (SELECT count(*) FROM chat_generations WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS n
    """).fetchone()['n']
    if pending >= 20:
        raise HTTPException(409, 'The queue is full. Wait or cancel an existing task.')

    ident = uuid.uuid4()
    conn.execute("""
        INSERT INTO runs(id,project_id,agent_id,agent_version,instructions,prompt,model,status,
                         requested_by,runtime_mode,tools,connection_id,request_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s,%s,%s,%s)
    """, (ident, project_id, agent['id'], agent['version'], agent['instructions'], prompt, model,
          user_id, agent['runtime_mode'], Jsonb(agent['tools']), connection_id, request_id))
    detail = {'agent_version': agent['version']}
    if connection_id is not None:
        detail['connection_id'] = str(connection_id)
    db.event('run.queued', user_id, detail, ident, conn)
    return ident
