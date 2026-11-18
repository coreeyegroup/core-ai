"""Local administrator credential preparation; no plaintext credential persistence."""
import hashlib
import re
import secrets


def prepare(username, password):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9_@.\-]{1,63}', username):
        raise ValueError('Use a username of 2–64 lowercase letters, digits, @, dots, underscores or hyphens.')
    # Explicit local reset supports user-selected short passwords. Normal bootstrap
    # continues to require 12 characters; this does not weaken other login controls.
    if not 6 <= len(password) <= 256 or any(c in password for c in ('\n', '\r', '\0')):
        raise ValueError('Use a password of 6–256 characters without line breaks.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return {'username': username, 'password_hash': f'scrypt${salt}${digest}'}


RESET_CODE = '''import json,sys
from core_ai import db
x=json.load(sys.stdin)
with db.connect() as conn:
    rows=conn.execute('SELECT id FROM users ORDER BY created_at FOR UPDATE').fetchall()
    if len(rows)!=1:
        raise SystemExit('Expected one CORE-AI administrator. No account was changed.')
    user_id=rows[0]['id']
    conn.execute('UPDATE users SET username=%s,password_hash=%s,enabled=true,failed_attempts=0,locked_until=NULL WHERE id=%s',
                 (x['username'],x['password_hash'],user_id))
    conn.execute('DELETE FROM sessions WHERE user_id=%s',(user_id,))
    db.event('administrator.credentials_changed','local-administrator',{'username':x['username']},conn=conn)
print('CORE-AI administrator credentials updated. Sign in again; previous sessions were revoked.')
'''
