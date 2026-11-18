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
    return row['value'] if row else {'endpoint': os.environ.get('CORE_AI_MODEL_URL', 'http://127.0.0.1:11434'), 'model': 'qwen3:4b'}

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


def inspect_model(name):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',name):raise ValueError('Invalid model name.')
    with httpx.Client(timeout=12,trust_env=False,follow_redirects=False) as client:
        r=client.post(config()['endpoint']+'/api/show',json={'model':name})
        r.raise_for_status();data=r.json()
    return {'model':name,'capabilities':data.get('capabilities',[]),'details':data.get('details',{}),'parameters':data.get('parameters',''),
            'context_windows':{k:v for k,v in data.get('model_info',{}).items() if k.endswith('.context_length')},
            'license':data.get('license','')[:20000]}


def metrics(data,started):
    import time
    result={'duration_ms':round((time.monotonic()-started)*1000)}
    for key in ('eval_count','eval_duration','prompt_eval_count','prompt_eval_duration','load_duration','total_duration'):
        value=data.get(key)
        if isinstance(value,(int,float)) and value>=0:result[key]=value
    if result.get('eval_duration',0)>0 and result.get('eval_count',0)>0:
        result['tokens_per_second']=round(result['eval_count']/(result['eval_duration']/1e9),2)
    return result
