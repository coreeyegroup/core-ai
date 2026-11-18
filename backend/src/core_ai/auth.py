"""Local passwords, revocable opaque sessions and same-origin CSRF protection."""
import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from . import db

COOKIE = 'core_ai_session'

def password_hash(password):
    if not 12 <= len(password) <= 256:
        raise ValueError('Use a password between 12 and 256 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'

def password_ok(password, stored):
    try:
        scheme, salt, digest = stored.split('$')
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return scheme == 'scrypt' and hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def origin_check(request):
    expected = os.environ.get('CORE_AI_ORIGIN', 'http://127.0.0.1:18787')
    if request.headers.get('origin') != expected:
        raise HTTPException(403, 'This operation requires the workstation origin.')

def session(request: Request):
    token = request.cookies.get(COOKIE, '')
    row = db.query('''SELECT u.id, u.username, s.csrf FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=%s AND s.expires_at>now() AND u.enabled''', (token_hash(token),), one=True)
    if not row:
        raise HTTPException(401, 'Sign in to CORE-AI.')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin_check(request)
        if not hmac.compare_digest(request.headers.get('x-core-ai-csrf', ''), row['csrf']):
            raise HTTPException(403, 'Session verification failed. Refresh and retry.')
    return row

def seed(username, password):
    with db.connect() as conn:
        if conn.execute('SELECT id FROM users LIMIT 1').fetchone():
            return False
        conn.execute('INSERT INTO users(id,username,password_hash) VALUES (%s,%s,%s)',
                     (uuid.uuid4(), username, password_hash(password)))
        db.event('administrator.created', detail={'username': username}, conn=conn)
    return True

def login(username, password):
    # A fixed dummy scrypt workload also runs for unknown usernames.
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE username=%s FOR UPDATE', (username,)).fetchone()
        valid = password_ok(password, row['password_hash'] if row else 'scrypt$missing$' + '0'*128)
        locked = row and row['locked_until'] and row['locked_until'] > datetime.now(timezone.utc)
        if not row or not row['enabled'] or locked or not valid:
            if row and not locked:
                conn.execute('''UPDATE users SET failed_attempts=failed_attempts+1,
                    locked_until=CASE WHEN failed_attempts>=4 THEN now()+interval '5 minutes' ELSE NULL END
                    WHERE id=%s''', (row['id'],))
            db.event('session.denied', detail={'username': username[:64]}, conn=conn)
            failure = True
        else:
            failure = False
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            conn.execute('UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=%s', (row['id'],))
            conn.execute('DELETE FROM sessions WHERE expires_at<=now()')
            conn.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES (%s,%s,%s,now()+interval '8 hours')",
                         (token_hash(token), row['id'], csrf))
            db.event('session.created', row['id'], conn=conn)
    if failure:
        raise HTTPException(401, 'Invalid credentials or account temporarily locked.')
    return token, {'username': row['username'], 'csrf': csrf}
