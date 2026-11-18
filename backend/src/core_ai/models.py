"""Private Ollama adapter. Endpoints are administrator configured, never supplied by prompts."""
import ipaddress
import os
from urllib.parse import urlsplit
import httpx
from psycopg.types.json import Jsonb
from . import db

def validate_endpoint(value):
    url = urlsplit(value)
    if url.scheme != 'http' or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('Use http:// followed by a private IPv4 address and port, without a path.')
    try:
        ip = ipaddress.IPv4Address(url.hostname)
        port = url.port or 80
    except (ValueError, TypeError):
        raise ValueError('A private IPv4 address is required.') from None
    allowed = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8')
    if not any(ip in ipaddress.IPv4Network(n) for n in allowed) or not 1 <= port <= 65535:
        raise ValueError('Only private or loopback model endpoints are allowed.')
    return f'http://{ip}:{port}'

def config():
    row = db.query("SELECT value FROM settings WHERE key='inference'", one=True)
    return row['value'] if row else {'endpoint': os.environ.get('CORE_AI_MODEL_URL', 'http://10.203.0.2:11434'), 'model': 'qwen3:4b'}

def configure(endpoint, model):
    endpoint = validate_endpoint(endpoint)
    db.query("INSERT INTO settings(key,value) VALUES ('inference',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (Jsonb({'endpoint': endpoint, 'model': model}),))

def list_models():
    cfg = config()
    with httpx.Client(timeout=8, trust_env=False, follow_redirects=False) as client:
        response = client.get(cfg['endpoint'] + '/api/tags')
        response.raise_for_status()
        items = response.json().get('models', [])
    return {'available': True, 'models': items, 'config': cfg}
