"""Short PostgreSQL transactions, one product database, no cross-product tables."""
import hashlib
import os
from pathlib import Path
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

@contextmanager
def connect():
    with psycopg.connect(os.environ['CORE_AI_DATABASE_URL'], row_factory=dict_row, connect_timeout=5) as conn:
        yield conn

def query(sql, params=(), *, one=False):
    with connect() as conn:
        cur = conn.execute(sql, params)
        if cur.description:
            return cur.fetchone() if one else cur.fetchall()

def event(action, actor='system', detail=None, run_id=None, conn=None):
    args = (run_id, str(actor), action, Jsonb(detail or {}))
    sql = 'INSERT INTO events(run_id,actor,action,detail) VALUES (%s,%s,%s,%s)'
    if conn is not None:
        conn.execute(sql, args)
    else:
        query(sql, args)

def migrate(root=None):
    root = root or Path(__file__).resolve().parents[2] / 'sql'
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(187875434)')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL)')
        for path in sorted(root.glob('*.sql')):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            old = conn.execute('SELECT checksum FROM schema_migrations WHERE name=%s', (path.name,)).fetchone()
            if old:
                if old['checksum'] != digest:
                    raise RuntimeError('Applied migration changed: ' + path.name)
                continue
            conn.execute(path.read_text())
            conn.execute('INSERT INTO schema_migrations VALUES (%s,%s)', (path.name, digest))
