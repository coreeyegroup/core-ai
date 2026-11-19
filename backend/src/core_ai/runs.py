"""Shared queue admission for workspace and automation jobs."""
import uuid

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from . import db


def enqueue(conn, *, project_id, agent, prompt, model, user_id, connection_id=None, request_id=None,
            timeout_seconds=300, max_output_tokens=2048):
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
                         requested_by,runtime_mode,tools,connection_id,request_id,timeout_seconds,max_output_tokens)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s,%s,%s,%s,%s,%s)
    """, (ident, project_id, agent.get('id'), agent.get('version'), agent.get('instructions', ''), prompt, model,
          user_id, agent.get('runtime_mode', 'analysis'), Jsonb(agent.get('tools', [])), connection_id, request_id,
          timeout_seconds, max_output_tokens))
    detail = {'agent_version': agent.get('version')}
    if connection_id is not None:
        detail['connection_id'] = str(connection_id)
    db.event('run.queued', user_id, detail, ident, conn)
    return ident
