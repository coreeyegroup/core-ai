"""Administrator-managed HTTPS connections with bounded, explicit execution."""
import base64
import ipaddress
import json
import os
import re
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import parse_qsl, quote, unquote, urlsplit

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr

from . import access, auth, db, key_storage

router = APIRouter(prefix='/api/v1/external-connections')
User = Annotated[dict, Depends(auth.session)]
MAX_RESPONSE = 512 * 1024
MAX_SOURCE = 48_000
SENSITIVE = re.compile(r'(?i)(token|password|authorization|secret|cookie|api[-_]?key|signature|credential|private[-_]?key)')
HEADER = re.compile(r'[A-Za-z][A-Za-z0-9-]{0,63}')
GRAPH = r'/v\d+\.\d+/'
UPSTOX_DATA_PATH = (
    r'/(?:v2/(?:option/(?:chain|contract)|market-quote/(?:quotes|ltp)|'
    r'order/(?:retrieve-all|details|history|trades(?:/get-trades-for-day)?)|'
    r'portfolio/(?:short-term-positions|long-term-holdings)|user/(?:profile|get-funds-and-margin|ip))|'
    r'v3/(?:market-quote/(?:ltp|quotes|ohlc|option-greek)|historical-candle/[A-Za-z0-9|_. &%/-]+))'
)
PROVIDERS = {
    'http': ('Custom HTTPS API', '', '', 'none', 'GET'),
    'n8n': ('n8n webhook', '', '/webhook/', 'header', 'POST'),
    'instagram': ('Instagram professional account', 'graph.instagram.com', GRAPH+r'(?:me(?:/media)?|\d+(?:/media)?)', 'bearer', 'GET'),
    'facebook': ('Facebook Pages', 'graph.facebook.com', GRAPH+r'(?:me/accounts|\d+(?:/posts|/feed)?)', 'bearer', 'GET'),
    'whatsapp': ('WhatsApp Business', 'graph.facebook.com', GRAPH+r'\d+(?:/phone_numbers)?', 'bearer', 'GET'),
    'twelvedata': ('Twelve Data · International Forex', 'api.twelvedata.com', r'/(?:time_series|quote|price|forex_pairs)', 'apikey', 'GET'),
    'upstox': ('Upstox · India market data', 'api.upstox.com', UPSTOX_DATA_PATH, 'bearer', 'GET'),
    'corei': ('Corei OS Mini · Market data', '', r'/api/research/v1/(?:capabilities|bars)', 'bearer', 'GET'),
}
Provider = Literal['http', 'n8n', 'instagram', 'facebook', 'whatsapp', 'twelvedata', 'upstox', 'corei']
Authentication = Literal['none', 'bearer', 'header', 'basic', 'apikey']
PUBLIC_COLUMNS = '''id,name,provider,endpoint,method,auth,header_name,paused,version,created_at,
                    secret IS NOT NULL AS has_secret,last_started_at'''


class ExternalConnection(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: Provider
    endpoint: str = Field(min_length=1, max_length=2048)
    method: Literal['GET', 'POST', 'PUT', 'PATCH'] = 'GET'
    auth: Authentication = 'none'
    header_name: str = Field(default='', max_length=64)
    secret: SecretStr | None = Field(default=None, max_length=4096)
    paused: bool = False
    version: int | None = Field(default=None, ge=1)


class RequestOptions(BaseModel):
    body: dict | list | None = None
    confirmed: bool = False
    project_id: uuid.UUID | None = None
    source_path: str = Field(default="", max_length=200, pattern=r"^[A-Za-z0-9_.-]*$")
    row_limit: int | None = Field(default=None, ge=1, le=500)


class UpstreamError(Exception):
    def __init__(self, outcome, status=None):
        self.outcome, self.status = outcome, status


def validated_url(provider, value, method, mode, header):
    try:
        parsed = urlsplit(value)
        url = httpx.URL(value)
        if (parsed.scheme != 'https' or not parsed.hostname or not url.host or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None or parsed.fragment
                or any(ord(char) < 32 or ord(char) == 127 for char in value) or '\\' in value or '%' in parsed.netloc):
            raise ValueError
        path = unquote(url.path)
        if ('\\' in path or '%' in path or any(ord(char) < 32 for char in path)
                or any(segment in ('.', '..') for segment in path.split('/'))
                or any(SENSITIVE.search(key) for key, _ in parse_qsl(parsed.query, max_num_fields=32))):
            raise ValueError
        _, host, allowed_path, expected_auth, expected_method = PROVIDERS[provider]
        if host and url.host != host:
            raise ValueError
        if provider == 'n8n' and (not path.startswith(allowed_path) or path == allowed_path or method != 'POST'):
            raise ValueError
        if provider not in ('http', 'n8n') and (
                method != expected_method or mode != expected_auth or not re.fullmatch(allowed_path, path)):
            raise ValueError
        if mode == 'header' and (not HEADER.fullmatch(header) or re.match(
                r'(?i)^(host|connection|content-|transfer-|cookie|set-cookie|forwarded|x-forwarded-|accept|proxy-|x-core-ai-)', header)):
            raise ValueError
        if mode == 'apikey' and provider != 'twelvedata':
            raise ValueError
    except (ValueError, httpx.InvalidURL):
        raise HTTPException(422, 'Enter a supported HTTPS endpoint, method and authentication configuration. Keep credentials out of the URL.') from None
    return url


def storage_cipher():
    try:
        material = base64.b64decode(os.environ[key_storage.ENV_KEY], validate=True)
        if len(material) < 32:
            raise ValueError
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=b'core-ai/external-connection-credentials/v1').derive(material)
        return AESGCM(key)
    except (KeyError, ValueError):
        raise HTTPException(503, 'Encrypted credentials are unavailable. Check the workstation key configuration.') from None


def encrypt(ident, value):
    nonce = os.urandom(12)
    return nonce + storage_cipher().encrypt(nonce, value.encode(), ident.bytes)


def decrypt(ident, encrypted):
    try:
        value = bytes(encrypted)
        return storage_cipher().decrypt(value[:12], value[12:], ident.bytes).decode()
    except (InvalidTag, ValueError):
        raise HTTPException(503, 'The saved credential cannot be read. Replace it in connection settings.') from None


def request_headers(mode, header, secret):
    headers = {'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    if mode == 'bearer':
        headers['Authorization'] = 'Bearer ' + secret
    elif mode == 'apikey':
        headers['Authorization'] = 'apikey ' + secret
    elif mode == 'basic':
        headers['Authorization'] = 'Basic ' + base64.b64encode(secret.encode()).decode()
    elif mode == 'header':
        headers[header] = secret
    return headers


def public_address(host):
    try:
        results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = [ipaddress.ip_address(result[4][0]) for result in results]
    except (OSError, ValueError):
        raise UpstreamError('dns_unavailable') from None
    if not addresses or any(not ip.is_global or ip.is_multicast or ip.is_reserved or
                            getattr(ip, 'ipv4_mapped', None) for ip in addresses):
        raise UpstreamError('destination_blocked')
    return str(next((ip for ip in addresses if ip.version == 4), addresses[0]))


def redact(value, credential):
    if isinstance(value, dict):
        return {str(redact(key, credential)): '[redacted]' if SENSITIVE.search(key) else redact(item, credential)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, credential) for item in value]
    if isinstance(value, str) and credential:
        for candidate in (credential, quote(credential, safe=''), base64.b64encode(credential.encode()).decode()):
            value = value.replace(candidate, '[redacted]')
        return value
    return value


def reject_json_constant(_):
    raise ValueError('Non-finite JSON number.')


def send(url, method, headers, credential, body, *, probe=False):
    address = public_address(url.raw_host.decode())
    # Pin the checked address. Retain original hostname for HTTP Host, TLS SNI and certificate validation.
    target = url.copy_with(host=address)
    headers = {**headers, 'Host': url.netloc.decode()}
    deadline = time.monotonic() + 12
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=4.0), trust_env=False,
                          follow_redirects=False) as client:
            with client.stream(method, target, headers=headers, content=body,
                               extensions={'sni_hostname': url.raw_host.decode()}) as response:
                status = response.status_code
                if not response.is_success:
                    raise UpstreamError('upstream_rejected', status)
                if probe or status == 204:
                    return status, None
                if response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                    raise UpstreamError('unsupported_encoding', status)
                raw = bytearray()
                for chunk in response.iter_raw():
                    raw.extend(chunk)
                    if len(raw) > MAX_RESPONSE:
                        raise UpstreamError('response_too_large', status)
                    if time.monotonic() > deadline:
                        raise UpstreamError('timeout', status)
                if not raw:
                    return status, None
                document = json.loads(raw, parse_constant=reject_json_constant)
                if isinstance(document, dict) and (document.get('error') or document.get('status') in ('error', 'failed')):
                    raise UpstreamError('provider_error', status)
                document = redact(document, credential)
                json.dumps(document, ensure_ascii=False, allow_nan=False).encode()
                return status, document
    except httpx.TimeoutException:
        raise UpstreamError('timeout') from None
    except (httpx.HTTPError, OSError):
        raise UpstreamError('transport_error') from None
    except (ValueError, RecursionError):
        raise UpstreamError('invalid_json') from None


def save_fields(ident, body, previous=None):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, 'Enter a connection name.')
    url = validated_url(body.provider, body.endpoint.strip(), body.method, body.auth, body.header_name)
    supplied = body.secret.get_secret_value() if body.secret is not None else ''
    encrypted = None
    header = body.header_name if body.auth == 'header' else ''
    if body.auth != 'none':
        if supplied:
            if any(not 32 <= ord(char) <= 126 for char in supplied) or not supplied.strip() or (
                    body.auth == 'basic' and ':' not in supplied):
                raise HTTPException(422, 'Enter a credential in the required format.')
            if supplied in str(url) or supplied in name:
                raise HTTPException(422, 'Keep the credential only in the credential field.')
            encrypted = encrypt(ident, supplied)
        elif previous:
            prior_url = httpx.URL(previous['endpoint'])
            if (previous['auth'], previous['provider'], previous['header_name'], previous['method'],
                    prior_url.host, prior_url.path) == (body.auth, body.provider, header, body.method, url.host, url.path):
                encrypted = previous['secret']
        if not encrypted:
            raise HTTPException(422, 'Enter a credential for this connection. Endpoint or authentication changes require re-entry.')
    return name, body.provider, str(url), body.method, body.auth, header, encrypted, body.paused


@router.get('')
def list_external(user: User):
    access.admin(user)
    return db.query(f'SELECT {PUBLIC_COLUMNS} FROM external_api_connections ORDER BY name,id')


@router.post('', status_code=201)
def create_external(body: ExternalConnection, user: User):
    access.admin(user)
    ident = uuid.uuid4()
    fields = save_fields(ident, body)
    with db.connect() as conn:
        conn.execute('''INSERT INTO external_api_connections
            (id,name,provider,endpoint,method,auth,header_name,secret,paused,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (ident, *fields, user['id']))
        db.event('external_connection.created', user['id'], {'id':str(ident)}, conn=conn)
    return {'id': ident}


@router.put('/{ident}')
def update_external(ident: uuid.UUID, body: ExternalConnection, user: User):
    access.admin(user)
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM external_api_connections WHERE id=%s FOR UPDATE', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Connection not found.')
        if body.version != row['version']:
            raise HTTPException(409, 'The connection changed. Refresh and edit it again.')
        fields = save_fields(ident, body, row)
        conn.execute('''UPDATE external_api_connections SET name=%s,provider=%s,endpoint=%s,method=%s,auth=%s,
                     header_name=%s,secret=%s,paused=%s,version=version+1 WHERE id=%s''', (*fields, ident))
        db.event('external_connection.updated', user['id'], {'id':str(ident)}, conn=conn)
    return {'id': ident}


@router.delete('/{ident}')
def delete_external(ident: uuid.UUID, user: User):
    access.admin(user)
    with db.connect() as conn:
        if not conn.execute('DELETE FROM external_api_connections WHERE id=%s RETURNING id', (ident,)).fetchone():
            raise HTTPException(404, 'Connection not found.')
        db.event('external_connection.deleted', user['id'], {'id':str(ident)}, conn=conn)
    return {'ok': True}


@router.get('/{ident}/activity')
def external_activity(ident: uuid.UUID, user: User):
    access.admin(user)
    return db.query('''SELECT id,occasion,outcome,upstream_status,elapsed_ms,occurred_at FROM external_api_activity
                    WHERE connection_id=%s ORDER BY id DESC LIMIT 30''', (ident,))


def source_payload(data, path, row_limit):
    for segment in path.split('.') if path else ():
        if not isinstance(data, dict) or not segment or segment not in data:
            raise ValueError('The source path is unavailable.')
        data = data[segment]
    if row_limit is not None:
        if not isinstance(data, list):
            raise ValueError('A row limit requires an array.')
        data = data[:row_limit]
    return data


@router.post('/{ident}/{occasion}')
def execute_external(ident: uuid.UUID, occasion: Literal['test', 'run'], options: RequestOptions, user: User):
    access.admin(user)
    probe = occasion == 'test'
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM external_api_connections WHERE id=%s FOR UPDATE', (ident,)).fetchone()
        if not row:
            raise HTTPException(404, 'Connection not found.')
        if row['paused']:
            raise HTTPException(409, 'Resume the connection before using it.')
        if (options.source_path or options.row_limit) and not options.project_id:
            raise HTTPException(422, 'Choose a project before setting snapshot options.')
        if options.project_id and (probe or row['method'] != 'GET'):
            raise HTTPException(422, 'Only a GET run can save a project source.')
        if options.project_id:
            access.project(conn, user, options.project_id, True)
        if not probe and row['method'] != 'GET' and not options.confirmed:
            raise HTTPException(422, 'Confirm the external action before sending the request.')
        if options.body is not None and (probe or row['method'] == 'GET'):
            raise HTTPException(422, 'The selected request does not accept a JSON body.')
        try:
            payload = None if options.body is None else json.dumps(options.body, allow_nan=False).encode()
        except (ValueError, RecursionError):
            raise HTTPException(422, 'Enter a valid JSON object or array.') from None
        if payload and len(payload) > 32_768:
            raise HTTPException(413, 'Request body exceeds 32 KB.')
        url = validated_url(row['provider'], row['endpoint'], row['method'], row['auth'], row['header_name'])
        credential = decrypt(ident, row['secret']) if row['secret'] else ''
        if row['last_started_at'] and (datetime.now(timezone.utc)-row['last_started_at']).total_seconds() < 2:
            raise HTTPException(429, 'Wait two seconds before running this connection again.', headers={'Retry-After':'2'})
        conn.execute('UPDATE external_api_connections SET last_started_at=now() WHERE id=%s', (ident,))
    headers = request_headers(row['auth'], row['header_name'], credential)
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    start = time.monotonic()
    # A write connection's test uses HEAD and cannot trigger its configured method.
    method = 'HEAD' if probe and row['method'] != 'GET' else row['method']
    try:
        status, data = send(url, method, headers, credential, payload, probe=(method == 'HEAD'))
        outcome = 'ok'
    except UpstreamError as exc:
        status, data, outcome = exc.status, None, exc.outcome
    elapsed = int((time.monotonic()-start)*1000)
    source_id = None
    with db.connect() as conn:
        current = conn.execute('SELECT version,paused FROM external_api_connections WHERE id=%s FOR UPDATE', (ident,)).fetchone()
        if options.project_id and outcome == 'ok' and data is not None and current and not current['paused'] and current['version'] == row['version']:
            access.project(conn, user, options.project_id, True)
            try:
                selected_data = source_payload(data, options.source_path, options.row_limit)
                content = json.dumps({'provider':row['provider'], 'host':url.host, 'path':url.path,
                                      'fetched_at':datetime.now(timezone.utc).isoformat(),
                                      'source_path':options.source_path or None, 'row_limit':options.row_limit,
                                      'payload':selected_data}, ensure_ascii=True, indent=2)
            except ValueError:
                content = None
            if content is None:
                outcome = 'invalid_source_options'
            elif len(content) > MAX_SOURCE:
                outcome = 'source_too_large'
            else:
                source_id = uuid.uuid4()
                title = 'API snapshot · ' + row['name']
                conn.execute('INSERT INTO documents(id,project_id,title,content) VALUES (%s,%s,%s,%s)',
                             (source_id, options.project_id, title, content))
                conn.execute('INSERT INTO document_versions(document_id,project_id,version,title,content) VALUES (%s,%s,1,%s,%s)',
                             (source_id, options.project_id, title, content))
                db.event('external_connection.source_created', user['id'], {'id':str(ident),'source_id':str(source_id)}, conn=conn)
        elif options.project_id and outcome == 'ok':
            outcome = 'source_unavailable'
        if current:
            conn.execute('''INSERT INTO external_api_activity(connection_id,occasion,outcome,upstream_status,elapsed_ms)
                         VALUES (%s,%s,%s,%s,%s)''', (ident, occasion, outcome, status, elapsed))
            conn.execute('''DELETE FROM external_api_activity WHERE connection_id=%s AND id NOT IN
                         (SELECT id FROM external_api_activity WHERE connection_id=%s ORDER BY id DESC LIMIT 100)''', (ident,ident))
    return {'outcome':outcome,'upstream_status':status,'elapsed_ms':elapsed,'method':method,'data':None if probe else data,'source_id':source_id}
